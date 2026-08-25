import datetime
import json
import os
from enum import Enum
from logging.config import dictConfig
from typing import Any

import psycopg
import xmltodict
from celery import Celery, Task
from celery.signals import after_setup_logger
from celery.utils.log import get_task_logger
from datahugger import (
    DabarXmlSrcDataset,
    Dataset,
    DataverseJsonSrcDataset,
    FileEntry,
    HalJsonSrcDataset,
    ZenodoJsonSrcDataset,
    ZipEntry,
    resolve,
)
from fastembed import TextEmbedding
from jsonschema.validators import validate
from lxml import etree as ET
from opensearchpy import OpenSearch
from opensearchpy.helpers import BulkIndexError, bulk
from psycopg.rows import dict_row

from config.logging_config import LOGGING_CONFIG
from config.opensearch_config import OpenSearchConfig
from config.postgres_config import PostgresConfig
from utils import handle_xml, normalize_datacite_json
from utils.embedding_utils import (
    OpenSearchSourceWithEmbedding,
    SourceWithEmbeddingText,
    add_embeddings_to_source,
    get_embedding_text_from_fields,
    preprocess_batch,
)
from utils.queue_utils import HarvestEventQueue


@after_setup_logger.connect()  # type: ignore[untyped-decorator, unused-ignore]
def configurate_celery_task_logger(**kwargs: Any) -> None:
    # https://docs.celeryq.dev/en/latest/userguide/signals.html#after-setup-logger
    dictConfig(LOGGING_CONFIG)


logger = get_task_logger(__name__)

# OAI-PMH XML namespaces
OAI_RECORD = f'{handle_xml.OAI}:record'
OAI_METADATA = f'{handle_xml.OAI}:metadata'

EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL')
if not EMBEDDING_MODEL:
    raise ValueError('Missing EMBEDDING_MODEL environment variable')

FASTEMBED_CACHE_DIR = os.environ.get('FASTEMBED_CACHE_DIR', '/root/.cache/fastembed')

celery_app = Celery('tasks')


# celery_app.task_serializer = 'json'
# celery_app.ignore_result = False


class ProviderCode(str, Enum):
    DANS = 'DANS'
    ZENODO = 'ZENODO'
    HAL = 'HAL'
    DABAR = 'DABAR'
    SWISSUBASE = 'SWISS'


class FileMetadataTask(Task):  # type: ignore
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        # TODO: how to configure DB and not hard code?
        self.postgres_config = PostgresConfig(db=os.environ.get('FILE_DB'))

    def parse_checksum(self, file: FileEntry | ZipEntry) -> tuple[str | None, str | None]:
        if not file.checksum:
            return None, None

        algo = file.checksum[0][0].replace('sha1', 'sha-1').upper()
        value = file.checksum[0][1]
        return algo, value

    def make_file_entry(self, harvest_event: HarvestEventQueue, file: FileEntry) -> tuple[Any, ...]:

        checksum_type, checksum_value = self.parse_checksum(file)

        return (
            harvest_event.harvest_url,
            harvest_event.record_identifier,
            file.file_identifier or file.filename,
            file.filename or file.file_identifier,
            'datahugger',
            harvest_event.identifier_type,
            'Dataset',
            file.mimetype,
            file.size,
            checksum_type,
            checksum_value,
            file.version,
            file.download_url,
            file.creation_date,
            file.last_modification_date,
        )

    def make_zip_entry(self, harvest_event: HarvestEventQueue, zip_file: ZipEntry) -> tuple[Any, ...]:
        checksum_type, checksum_value = self.parse_checksum(zip_file)

        return (
            harvest_event.harvest_url,
            harvest_event.record_identifier,
            harvest_event.record_identifier,
            harvest_event.record_identifier,
            'datahugger',
            harvest_event.identifier_type,
            'Dataset',
            'application/zip',
            None,
            checksum_type,
            checksum_value,
            zip_file.version,
            zip_file.download_url,
            zip_file.creation_date,
            None,
        )

    def collect_files(self, harvest_event: HarvestEventQueue, dataset: Dataset) -> list[tuple[Any, ...]]:
        return [self.make_file_entry(harvest_event, file) for file in dataset.crawl_file()]


@celery_app.task(bind=True, base=FileMetadataTask, ignore_result=True)
def add_file_metadata(self: Any, batch: list[HarvestEventQueue]) -> int:

    success = 0

    with psycopg.connect(**self.postgres_config.connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        for ele in batch:
            files = []
            harvest_event = HarvestEventQueue(*ele)  # reconstruct HarvestEvent from serialized list

            if (
                harvest_event.additional_metadata_API
                and harvest_event.additional_metadata
                and harvest_event.additional_metadata_protocol == 'DATAVERSE_API'
            ):
                # this only covers dataverse for now

                url = harvest_event.additional_metadata_API.replace(
                    '/api/datasets/:persistentId/versions/:latest-published',
                    f'/dataset.xhtml?persistentId=doi:{harvest_event.record_identifier}',
                )

                ds_dv = DataverseJsonSrcDataset(url, harvest_event.additional_metadata)

                files.extend(self.collect_files(harvest_event, ds_dv))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.ZENODO:
                # get id from DOI: 10.5281/zenodo.570959 -> 570959
                ds_z = ZenodoJsonSrcDataset(
                    harvest_event.record_identifier.split('.')[-1], harvest_event.additional_metadata
                )

                files.extend(self.collect_files(harvest_event, ds_z))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.HAL:
                # HAL IDs contain a version suffix, needs to be removed
                ds_hal = HalJsonSrcDataset(
                    harvest_event.record_identifier.split('v')[0], harvest_event.additional_metadata
                )

                files.extend(self.collect_files(harvest_event, ds_hal))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.DABAR:
                ds_dabar = DabarXmlSrcDataset('', harvest_event.additional_metadata)

                files.extend(self.collect_files(harvest_event, ds_dabar))

            elif harvest_event.code == ProviderCode.SWISSUBASE:
                ds_swiss = resolve(
                    f'https://www.swissubase.ch/en/catalogue/studies/1223/latest/datasets/114/{harvest_event.record_identifier}/overview'
                )

                for zip_file in ds_swiss.crawl():
                    files.append(self.make_zip_entry(harvest_event, zip_file))

            if len(files) == 0:
                logger.debug(f'no files for {harvest_event.record_identifier} in {harvest_event.code}')
                continue
            success += 1

            # Delete existing file entries for this endpoint and endpoint
            # A new version could provide fewer files
            cur.execute(
                """
                DELETE FROM record_files
                WHERE harvest_url = %s AND record_identifier = %s
                """,
                (harvest_event.harvest_url, harvest_event.record_identifier),
            )

            sql = """
                    INSERT INTO record_files (
                        harvest_url,
                        record_identifier,
                        file_identifier,
                        file_name,
                        file_information_method,
                        identifier_type,
                        identifier_granularity,
                        file_type,
                        file_size,
                        checksum_type,
                        checksum_value,
                        file_version,
                        download_url,
                        file_created_at,
                        file_last_modified_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s::file_identifier_type,
                        %s::identifier_granularity_level,
                        %s, %s,
                        %s::checksum_algorithm,
                        %s, %s, %s,
                        %s::timestamp with time zone,
                        %s::timestamp with time zone
                    )
                """

            cur.executemany(sql, files)

    return success


class TransformTask(Task):  # type: ignore
    embedding_transformer: TextEmbedding
    client: OpenSearch
    schema: dict[Any, Any]
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        if EMBEDDING_MODEL:
            self.embedding_transformer = TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=FASTEMBED_CACHE_DIR)
            logger.info(f'Setting up embedding transformer with model {EMBEDDING_MODEL}')

        opensearch_config = OpenSearchConfig()
        self.client = OpenSearch(
            hosts=[{'host': opensearch_config.host, 'port': opensearch_config.port}],
            http_auth=None,
            use_ssl=False,
            logger=logger,
        )

        self.postgres_config = PostgresConfig()

        with open('../config/schema.json') as f:
            self.schema = json.load(f)


@celery_app.task(base=TransformTask, bind=True, ignore_result=True)
def transform_batch(self: Any, batch: list[HarvestEventQueue], index_name: str, reuse_embeddings: bool) -> Any:
    if not self.client.indices.exists(index=index_name):
        raise ValueError(f'Index {index_name} does not exist in OpenSearch')

    # transform to JSON and normalize

    # Error handling: if an error is thrown, psycopg will roll back the whole transaction and the whole batch fails because the exception is re-raised,
    # making sure that only the whole batch is synced with PostgreSQL. See https://www.psycopg.org/psycopg3/docs/basic/transactions.html:
    # "Thankfully, if you use the connection context, Psycopg will commit the connection at the end of the block
    # (or roll it back if the block is exited with an exception)"
    # However, this is not true for OpenSearch since we use a different client to write or delete data in OpenSearch and this actions will take immediate effect.
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
                    id = record_to_delete['id']
                    doi = record_to_delete.get('doi')

                    opensearch_id = doi if doi is not None else record_to_delete['url']

                    try:
                        # delete document from OpenSearch
                        self.client.delete(
                            index=index_name,
                            id=opensearch_id,
                            ignore=404,
                            # https://github.com/opensearch-project/opensearch-py/blob/4ef46e5c17234e3e9b09338c98a599e18d42f572/guides/document_lifecycle.md
                        )
                    except Exception as e:
                        logger.warning(f'Failed to delete {opensearch_id} from OpenSearch: {e}')
                        raise e

                    # delete record in DB
                    cur.execute(
                        """
                    DELETE FROM records WHERE id = %s;
                    """,
                        [id],
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
            src_with_emb: list[OpenSearchSourceWithEmbedding] = []
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
                        OpenSearchSourceWithEmbedding(
                            src={
                                **normalized_ele.src,
                                'emb': row['embeddings'],
                                '_additional_metadata': normalized_ele.event.additional_metadata,
                                '_repo': normalized_ele.event.code,
                                '_harvest_url': normalized_ele.event.harvest_url,
                            },
                            harvest_event=normalized_ele.event,
                        )
                    )
            else:
                logger.info(f'About to Calculate embeddings for {len(normalized)}')
                src_with_emb = add_embeddings_to_source(normalized, self.embedding_transformer)
                logger.info(f'Calculated embeddings for {len(src_with_emb)}')
            preprocessed = preprocess_batch([src_with_emb_ele.src for src_with_emb_ele in src_with_emb], index_name)
        except Exception as e:
            logger.error(f'Could not calculate embeddings: {e}')
            raise e

        try:
            success, failed = bulk(self.client, preprocessed)
            if success < len(src_with_emb):
                logger.error(
                    f'Normalized doc size was {len(src_with_emb)} but only {success} were imported into OpenSearch.'
                )

            opensearch_synced_at = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f%z')
            logger.info(f'Bulk results: success {success} failed: {failed}')

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
                embeddings = rec.src['emb']
                datacite_json = json.dumps({**rec.src, 'emb': None})
                opensearch_synced = True
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
                        opensearch_synced,
                        opensearch_synced_at,
                        additional_metadata,
                        datestamp
                    ) 
                    VALUES (
                        %s, %s, %s, %s, %s, XMLPARSE(DOCUMENT %s), %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                        opensearch_synced_at = EXCLUDED.opensearch_synced_at,
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
                        opensearch_synced,
                        opensearch_synced_at,
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

        except BulkIndexError as e:
            logger.error(f'OpenSearch bulk indexing failed: {e}')
            raise e
        except Exception as e:
            logger.error(f'Writing batch failed: {e}')
            raise e

    return success
