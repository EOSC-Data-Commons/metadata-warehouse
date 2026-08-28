import json
import os
from typing import Any

import psycopg
import xmltodict
from celery import Task
from fastembed import TextEmbedding
from jsonschema.validators import validate
from lxml import etree as ET
from psycopg.rows import dict_row

from config.postgres_config import PostgresConfig
from transform.celery_app_def import celery_app, logger
from utils import handle_xml, normalize_datacite_json
from utils.embedding_utils import (
    SourceWithEmbedding,
    SourceWithEmbeddingText,
    add_embeddings_to_source,
    get_embedding_text_from_fields,
)
from utils.queue_utils import HarvestEventQueue

# OAI-PMH XML namespaces
OAI_RECORD = f'{handle_xml.OAI}:record'
OAI_METADATA = f'{handle_xml.OAI}:metadata'

EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL')
if not EMBEDDING_MODEL:
    raise ValueError('Missing EMBEDDING_MODEL environment variable')

FASTEMBED_CACHE_DIR = os.environ.get('FASTEMBED_CACHE_DIR', '/root/.cache/fastembed')


class TransformTask(Task):  # type: ignore
    embedding_transformer: TextEmbedding
    schema: dict[Any, Any]
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        if EMBEDDING_MODEL:
            self.embedding_transformer = TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=FASTEMBED_CACHE_DIR)
            logger.info(f'Setting up embedding transformer with model {EMBEDDING_MODEL}')

        self.postgres_config = PostgresConfig()

        with open('../config/schema.json') as f:
            self.schema = json.load(f)


@celery_app.task(base=TransformTask, bind=True, ignore_result=True)
def transform_batch(self: Any, batch: list[HarvestEventQueue], reuse_embeddings: bool) -> Any:
    # transform to JSON and normalize

    # Error handling: if an error is thrown, psycopg will roll back the whole transaction and the whole batch fails because the exception is re-raised,
    # making sure that only the whole batch is synced with PostgreSQL. See https://www.psycopg.org/psycopg3/docs/basic/transactions.html:
    # "Thankfully, if you use the connection context, Psycopg will commit the connection at the end of the block
    # (or roll it back if the block is exited with an exception)"
    with psycopg.connect(**self.postgres_config.connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        normalized: list[SourceWithEmbeddingText] = []
        for ele in batch:
            harvest_event = HarvestEventQueue(*ele)  # reconstruct HarvestEvent from serialized list

            if harvest_event.is_deleted:
                # find record in DB
                cur.execute(
                    """
                SELECT id, doi, url FROM records
                WHERE endpoint_id = %s and record_identifier = %s
                """,
                    (harvest_event.endpoint_id, harvest_event.record_identifier),
                )

                record_to_delete = cur.fetchone()

                if record_to_delete is not None:
                    rec_id = record_to_delete['id']

                    # delete record in DB
                    cur.execute(
                        """
                    DELETE FROM records WHERE id = %s;
                    """,
                        [rec_id],
                    )

                continue

            logger.debug(f'Processing {harvest_event}')

            # Catch and log errors
            try:
                root = ET.fromstring(harvest_event.xml.encode('utf-8'))
                metadata_ns = handle_xml.detect_metadata_namespace(root)
                payload_ns = handle_xml.detect_payload_namespace(root)
                contents = handle_xml.preprocess_xml(root)

                converted = xmltodict.parse(contents, process_namespaces=True)

                if OAI_RECORD in converted and OAI_METADATA in converted[OAI_RECORD]:
                    metadata = converted[OAI_RECORD][OAI_METADATA]
                    result = handle_xml.get_resource(metadata, metadata_ns, payload_ns)

                    if result is None:
                        # Converted JSON cannot be processed, log this
                        logger.debug(f'Cannot access resource element in {metadata} {harvest_event.record_identifier}')
                        continue

                    resource, metadata_namespace_for_access = result
                else:
                    # Converted JSON cannot be processed, log this
                    logger.debug(f'Cannot access {OAI_METADATA} in: {converted}')
                    continue

                logger.debug(contents)
                logger.debug(metadata_ns)

                normalized_record = normalize_datacite_json.normalize_datacite_json(
                    resource, metadata_namespace_for_access
                )
                validate(instance=normalized_record, schema=self.schema)
                normalized.append(
                    SourceWithEmbeddingText(
                        src=normalized_record,
                        textToEmbed=get_embedding_text_from_fields(normalized_record),
                        event=harvest_event,
                    )
                )

            except Exception as e:
                logger.info(
                    f'An error occurred for {harvest_event.record_identifier} in harvest_event {harvest_event.id} during transformation or validation: {e}'
                )

                cur.execute(
                    """
                    UPDATE harvest_events 
                    SET error_message = %s
                    WHERE id = %s  
                    """,
                    (str(e), harvest_event.id),
                )
                continue

        try:
            src_with_emb: list[SourceWithEmbedding] = []
            if reuse_embeddings:
                logger.info(f'Reusing embeddings from DB for {len(normalized)} records')
                for normalized_ele in normalized:
                    cur.execute(
                        """
                        SELECT embeddings FROM records
                        WHERE endpoint_id = %s AND record_identifier = %s
                        """,
                        (normalized_ele.event.endpoint_id, normalized_ele.event.record_identifier),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise ValueError(
                            f'No existing embeddings found for {normalized_ele.event.record_identifier} on endpoint {normalized_ele.event.endpoint_id}'
                        )
                    src_with_emb.append(
                        SourceWithEmbedding(
                            src=normalized_ele.src,
                            embedding=row['embeddings'],
                            harvest_event=normalized_ele.event,
                        )
                    )
            else:
                logger.info(f'About to Calculate embeddings for {len(normalized)}')
                src_with_emb = add_embeddings_to_source(normalized, self.embedding_transformer)
                logger.info(f'Calculated embeddings for {len(src_with_emb)}')
        except Exception as e:
            logger.error(f'Could not calculate embeddings: {e}')
            raise e

        try:
            for rec in src_with_emb:
                # write to records table

                record_identifier = rec.harvest_event.record_identifier
                datestamp = rec.harvest_event.datestamp
                repository_id = rec.harvest_event.repository_id
                endpoint_id = rec.harvest_event.endpoint_id
                resource_type = 'Dataset'  # TODO: get this information from record
                title = rec.src['titles'][0]['title']
                xml = rec.harvest_event.xml
                protocol = 'OAI-PMH'
                url = rec.src.get('url')
                embeddings = rec.embedding
                datacite_json = json.dumps(rec.src)
                additional_metadata = rec.harvest_event.additional_metadata

                # https://neon.com/postgresql/postgresql-tutorial/postgresql-upsert
                cur.execute(
                    """
                    INSERT INTO records 
                    (   
                        record_identifier,
                        repository_id,
                        endpoint_id,
                        resource_type,
                        title,
                        raw_metadata,
                        metadata_protocol,
                        url,
                        embeddings,
                        embedding_model,
                        datacite_json,
                        additional_metadata,
                        datestamp
                    ) 
                    VALUES (
                        %s, %s, %s, %s, %s, XMLPARSE(DOCUMENT %s), %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (endpoint_id, record_identifier)
                    DO UPDATE SET 
                        resource_type = EXCLUDED.resource_type,
                        title = EXCLUDED.title,
                        raw_metadata = EXCLUDED.raw_metadata,
                        url = EXCLUDED.url,
                        embeddings = EXCLUDED.embeddings,
                        embedding_model = EXCLUDED.embedding_model,
                        datacite_json = EXCLUDED.datacite_json,
                        additional_metadata = EXCLUDED.additional_metadata,
                        datestamp = EXCLUDED.datestamp
                    """,
                    (
                        record_identifier,
                        repository_id,
                        endpoint_id,
                        resource_type,
                        title,
                        xml,
                        protocol,
                        url,
                        embeddings,
                        EMBEDDING_MODEL,
                        datacite_json,
                        additional_metadata,
                        datestamp,
                    ),
                )

                cur.execute(
                    """
                    UPDATE harvest_events 
                    SET error_message = NULL
                    WHERE id = %s  
                    """,
                    [rec.harvest_event.id],
                )

        except Exception as e:
            logger.error(f'Writing batch failed: {e}')
            raise

    return len(src_with_emb)
