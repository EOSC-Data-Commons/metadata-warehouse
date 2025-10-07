import json
import os
from pathlib import Path
from config.logging_config import LOGGING_CONFIG
from logging.config import dictConfig
from fastembed import TextEmbedding
from celery import Celery, Task
from jsonschema.exceptions import ValidationError
from jsonschema.validators import validate
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, BulkIndexError
import xmltodict
from config.postgres_config import PostgresConfig
from utils.queue_utils import HarvestEvent
from utils.embedding_utils import preprocess_batch, add_embeddings_to_source, SourceWithEmbeddingText, \
    get_embedding_text_from_fields
from utils import normalize_datacite_json
from typing import Any
from celery.utils.log import get_task_logger
from celery.signals import after_setup_logger
import pgsql  # type: ignore
import datetime

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

        self.client = OpenSearch(
            hosts=[{'host': 'opensearch', 'port': 9200}],
            http_auth=None,
            use_ssl=False,
            logger=logger
        )

        self.postgres_config = PostgresConfig()

        with open('config/schema.json') as f:
            self.schema = json.load(f)


@celery_app.task(base=TransformTask, bind=True, ignore_result=True)
def transform_batch(self: Any, batch: list[HarvestEvent], index_name: str) -> Any:
    # transform to JSON and normalize

    logger.info(f'Starting processing batch of {len(batch)}')

    normalized: list[SourceWithEmbeddingText] = []
    for ele in batch:

        harvest_event = HarvestEvent(*ele) # reconstruct HravestEvent from serialized list

        #logger.info(f'Processing {ele[0]}')
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
        else:
            # JSON cannot be processed, log this
            logger.debug(f'Cannot access {DATACITE_RESOURCE} or {HAL_RESOURCE} in : {metadata}')
            continue

        # Catch and log errors
        try:
            normalized_record = normalize_datacite_json.normalize_datacite_json(resource)
            validate(instance=normalized_record, schema=self.schema)
            normalized.append(SourceWithEmbeddingText(src=normalized_record,
                                                      textToEmbed=get_embedding_text_from_fields(normalized_record),
                                                      file=Path(''),
                                                      event=harvest_event
                                                      ))
        except ValidationError as e:
            logger.info(f'Validation failed for {rec_id} in harvest_event {harvest_event.id}: {e.message}')
            with pgsql.Connection(('postgres', self.postgres_config.port), self.postgres_config.user,
                                  self.postgres_config.password,
                                  tls=False) as db:
                db.execute(
                    f"""
                    UPDATE harvest_events 
                    SET error_message = '{e.message.replace("'", "''")}'
                    WHERE id = '{harvest_event.id}'  
                    """
                )
            continue
        except Exception as e:
            logger.info(f'An error occurred for {rec_id} in harvest_event {harvest_event.id} during transformation: {e}')
            with pgsql.Connection(('postgres', self.postgres_config.port), self.postgres_config.user,
                                  self.postgres_config.password,
                                  tls=False) as db:

                db.execute(
                    f"""
                                    UPDATE harvest_events 
                                    SET error_message = '{str(e).replace("'", "''")}'
                                    WHERE id = '{harvest_event.id}'  
                                    """
                )
            continue

    try:
        logger.info(f'About to Calculate embeddings for {len(normalized)}')
        src_with_emb: list[tuple[dict[str, Any], SourceWithEmbeddingText]] = add_embeddings_to_source(normalized,
                                                                                   self.embedding_transformer)
        logger.info(f'Calculated embeddings for {len(src_with_emb)}')
        preprocessed = preprocess_batch(list(map(lambda el: el[0], src_with_emb)), index_name)
    except Exception as e:
        logger.error(f'Could not calculate embeddings: {e}')
        raise e

    try:
        success, failed = bulk(self.client, preprocessed)
        if success < len(src_with_emb):
            logger.error(f'Normalized doc size was {len(src_with_emb)} but only {len(success)} were imported into OpenSearch.')

        opensearch_synced_at = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f%z')
        logger.info(f'Bulk results: success {success} failed: {failed}')

        for rec in src_with_emb:
            # TODO: use a bulk method
            # TODO: use a better solution like SQLAlchemy to construct queries
            # write to records table

            if rec[1].event is None:
                raise ValueError(f'Original HarvestEvent not found')

            #logger.info(f'HarvestEvent: {rec[1].event}')

            with pgsql.Connection(('postgres', self.postgres_config.port), self.postgres_config.user, self.postgres_config.password,
                                  tls=False) as db:

                statements = f"""
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
                    opensearch_synced_at
                    ) 
                VALUES (
                    '{rec[1].event.record_identifier}',
                    '{rec[1].event.repository_id}',
                    '{rec[1].event.endpoint_id}',
                    'Dataset',
                    '{rec[0]['titles'][0]['title'].replace("'", "''")}',
                    '{rec[1].event.xml.replace("'", "''")}',
                    'OAI-PMH',
                    {'\'' + rec[0]['doi'] + '\'' if 'doi' in rec[0] else 'NULL' },
                    {'\'' + rec[0]['url'] + '\'' if 'url' in rec[0] else 'NULL' },
                    '{{ {', '.join([str(f) for f in rec[0]['emb']])} }}',
                    '{EMBEDDING_MODEL}',
                    '{json.dumps({**rec[0], 'emb': None}).replace("'", "''")}',
                    true,
                    '{opensearch_synced_at}'
                    )     
                """

                #logger.info(statements)

                res = db.execute(statements) # named tuple serialized as list in broker


    except BulkIndexError as e:
        logger.error(f'Bulk failed: {e}')
        raise e
    except Exception as e:
        logger.error(f'Writing batch failed: {e}')
        raise e

    return success
