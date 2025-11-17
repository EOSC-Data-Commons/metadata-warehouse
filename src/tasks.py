import json
import os
from pathlib import Path
from config.logging_config import LOGGING_CONFIG
from logging.config import dictConfig
from fastembed import TextEmbedding
from celery import Celery, Task
from jsonschema.validators import validate
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, BulkIndexError
import xmltodict
from config.postgres_config import PostgresConfig
from config.opensearch_config import OpenSearchConfig
from utils.queue_utils import HarvestEventQueue
from utils.embedding_utils import preprocess_batch, add_embeddings_to_source, SourceWithEmbeddingText, \
    get_embedding_text_from_fields, OpenSearchSourceWithEmbedding
from utils import normalize_datacite_json
from typing import Any
from celery.utils.log import get_task_logger
from celery.signals import after_setup_logger
import datetime
import psycopg
from psycopg.rows import dict_row

@after_setup_logger.connect()  # type: ignore
def configurate_celery_task_logger(**kwargs: Any) -> None:
    # https://docs.celeryq.dev/en/latest/userguide/signals.html#after-setup-logger
    dictConfig(LOGGING_CONFIG)


logger = get_task_logger(__name__)

# OAI-PMH XML namespaces
OAI = 'http://www.openarchives.org/OAI/2.0/'
OAI_RECORD = f'{OAI}:record'
OAI_METADATA = f'{OAI}:metadata'
DATACITE_RESOURCE = 'http://datacite.org/schema/kernel-4:resource'
HAL_RESOURCE = f'{OAI}:resource'
ONEDATA_WRAPPER = 'http://schema.datacite.org/oai/oai-1.1/:oai_datacite'
ONEDATA_PAYLOAD = 'http://schema.datacite.org/oai/oai-1.1/:payload'

EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL')
if not EMBEDDING_MODEL:
    raise ValueError('Missing EMBEDDING_MODEL environment variable')

celery_app = Celery('tasks')


# celery_app.task_serializer = 'json'
# celery_app.ignore_result = False

class TransformTask(Task):  # type: ignore

    embedding_transformer: TextEmbedding
    client: OpenSearch
    schema: dict[Any, Any]
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        if EMBEDDING_MODEL:
            self.embedding_transformer = TextEmbedding(model_name=EMBEDDING_MODEL)
            logger.info(f'Setting up embedding transformer with model {EMBEDDING_MODEL}')

        opensearch_config = OpenSearchConfig()
        self.client = OpenSearch(
            hosts=[{'host': opensearch_config.host, 'port': opensearch_config.port}],
            http_auth=None,
            use_ssl=False,
            logger=logger
        )

        self.postgres_config = PostgresConfig()

        with open('config/schema.json') as f:
            self.schema = json.load(f)


@celery_app.task(base=TransformTask, bind=True, ignore_result=True)
def transform_batch(self: Any, batch: list[HarvestEventQueue], index_name: str) -> Any:
    # transform to JSON and normalize

    # Error handling: if an error is thrown, psycopg will roll back the whole transaction and the whole batch fails because the exception is re-raised,
    # making sure that only the whole batch is synced with PostgreSQL. See https://www.psycopg.org/psycopg3/docs/basic/transactions.html:
    # "Thankfully, if you use the connection context, Psycopg will commit the connection at the end of the block
    # (or roll it back if the block is exited with an exception)"
    # However, this is not true for OpenSearch since we use a different client to write or delete data in OpenSearch and this actions will take immediate effect.
    with psycopg.connect(dbname=self.postgres_config.user, user=self.postgres_config.user, host=self.postgres_config.address,
                                         password=self.postgres_config.password, port=self.postgres_config.port,
                                         row_factory=dict_row) as conn:

        cur = conn.cursor()

        normalized: list[SourceWithEmbeddingText] = []
        for ele in batch:

            harvest_event = HarvestEventQueue(*ele) # reconstruct HarvestEvent from serialized list

            if harvest_event.is_deleted:
                # find record in DB
                cur.execute("""
                SELECT id, doi, url FROM records
                WHERE endpoint_id = %s and record_identifier = %s
                """, (harvest_event.endpoint_id, harvest_event.record_identifier))

                record_to_delete = cur.fetchone()

                if record_to_delete is not None:

                    id = record_to_delete['id']
                    doi = record_to_delete.get('doi')

                    opensearch_id = doi if doi is not None else record_to_delete['url']

                    try:
                        # delete document from OpenSearch
                        self.client.delete(
                            index=index_name,
                            id=opensearch_id,
                            ignore=404 # https://github.com/opensearch-project/opensearch-py/blob/4ef46e5c17234e3e9b09338c98a599e18d42f572/guides/document_lifecycle.md
                        )
                    except Exception as e:
                        logger.warning(f"Failed to delete {opensearch_id} from OpenSearch: {e}")
                        raise e

                    # delete record in DB
                    cur.execute("""
                    DELETE FROM records WHERE id = %s;
                    """, [id])


                continue

            logger.debug(f'Processing {harvest_event}')
            converted = xmltodict.parse(harvest_event.xml, process_namespaces=True)  # named tuple serialized as list in broker

            if OAI_RECORD in converted and OAI_METADATA in converted[OAI_RECORD]:
                rec_id = converted[OAI_RECORD][f'{OAI}:header'][
                    f'{OAI}:identifier']

                logger.debug(f'{rec_id}')

                metadata = converted[OAI_RECORD][OAI_METADATA]
            else:
                # Converted JSON cannot be processed, log this
                logger.debug(f'Cannot access {OAI_METADATA} in : {converted}')
                continue

            if DATACITE_RESOURCE in metadata:
                resource = metadata[DATACITE_RESOURCE]
            elif HAL_RESOURCE in metadata:
                # HAL
                resource = metadata[HAL_RESOURCE]
            elif ONEDATA_WRAPPER in metadata and ONEDATA_PAYLOAD in metadata[ONEDATA_WRAPPER] and DATACITE_RESOURCE in metadata[ONEDATA_WRAPPER][ONEDATA_PAYLOAD]:
                # extra layer structure from Onedata
                resource = metadata[ONEDATA_WRAPPER][ONEDATA_PAYLOAD][DATACITE_RESOURCE]
            else:
                # JSON cannot be processed, log this
                logger.debug(f'Cannot access resource element {DATACITE_RESOURCE} or {HAL_RESOURCE} or {ONEDATA_WRAPPER}{ONEDATA_PAYLOAD} in : {metadata}')
                continue

            # Catch and log errors
            try:
                normalized_record = normalize_datacite_json.normalize_datacite_json(resource)
                validate(instance=normalized_record, schema=self.schema)
                normalized.append(SourceWithEmbeddingText(src=normalized_record,
                                                          textToEmbed=get_embedding_text_from_fields(normalized_record),
                                                          event=harvest_event
                                                          ))

            except Exception as e:
                logger.info(f'An error occurred for {rec_id} in harvest_event {harvest_event.id} during transformation or validation: {e}')

                cur.execute(
                    """
                    UPDATE harvest_events 
                    SET error_message = %s
                    WHERE id = %s  
                    """, (str(e), harvest_event.id)
                )
                continue

        try:
            logger.info(f'About to Calculate embeddings for {len(normalized)}')
            src_with_emb: list[OpenSearchSourceWithEmbedding] = add_embeddings_to_source(normalized,
                                                                                       self.embedding_transformer)
            logger.info(f'Calculated embeddings for {len(src_with_emb)}')
            preprocessed = preprocess_batch([src_with_emb_ele.src for src_with_emb_ele in src_with_emb], index_name)
        except Exception as e:
            logger.error(f'Could not calculate embeddings: {e}')
            raise e

        try:
            success, failed = bulk(self.client, preprocessed)
            if success < len(src_with_emb):
                logger.error(f'Normalized doc size was {len(src_with_emb)} but only {success} were imported into OpenSearch.')

            opensearch_synced_at = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f%z')
            logger.info(f'Bulk results: success {success} failed: {failed}')

            for rec in src_with_emb:
                # write to records table

                record_identifier = rec.harvest_event.record_identifier
                datestamp = rec.harvest_event.datestamp
                repository_id = rec.harvest_event.repository_id
                endpoint_id = rec.harvest_event.endpoint_id
                resource_type = 'Dataset' # TODO: get this information from record
                title = rec.src['titles'][0]['title']
                xml = rec.harvest_event.xml
                protocol = 'OAI-PMH'
                doi = rec.src.get('doi')
                url = rec.src.get('url')
                embeddings = rec.src['emb']
                datacite_json = json.dumps({**rec.src, 'emb': None})
                opensearch_synced = True
                additional_metadata = rec.harvest_event.additional_metadata

                # https://neon.com/postgresql/postgresql-tutorial/postgresql-upsert
                cur.execute("""
                INSERT INTO records 
                (   
                    record_identifier,
                    repository_id,
                    endpoint_id,
                    resource_type,
                    title,
                    raw_metadata,
                    metadata_protocol,
                    doi,
                    url,
                    embeddings,
                    embedding_model,
                    datacite_json,
                    opensearch_synced,
                    opensearch_synced_at,
                    additional_metadata,
                    datestamp
                    ) 
                VALUES (
                    %s, %s, %s, %s, %s, XMLPARSE(DOCUMENT %s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (endpoint_id, record_identifier)
                    DO UPDATE SET resource_type = %s, title = %s, raw_metadata = XMLPARSE(DOCUMENT %s), doi = %s, url = %s, embeddings = %s, embedding_model = %s, datacite_json = %s, opensearch_synced_at = %s, additional_metadata = %s, datestamp = %s      
                """, (record_identifier, # Insert
                      repository_id,
                      endpoint_id,
                      resource_type,
                      title,
                      xml,
                      protocol,
                      doi,
                      url,
                      embeddings,
                      EMBEDDING_MODEL,
                      datacite_json,
                      opensearch_synced,
                      opensearch_synced_at,
                      additional_metadata,
                      datestamp,
                      resource_type, # Update
                      title,
                      xml,
                      doi,
                      url,
                      embeddings,
                      EMBEDDING_MODEL,
                      datacite_json,
                      opensearch_synced_at,
                      additional_metadata,
                      datestamp
                      )
                )

                cur.execute(
                    """
                    UPDATE harvest_events 
                    SET error_message = NULL
                    WHERE id = %s  
                    """, [rec.harvest_event.id]
                )

        except BulkIndexError as e:
            logger.error(f'OpenSearch bulk indexing failed: {e}')
            raise e
        except Exception as e:
            logger.error(f'Writing batch failed: {e}')
            raise e

    return success
