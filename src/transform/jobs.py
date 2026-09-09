"""The python jobs the airflow DAGs call, one function per unit of work.

Plain functions that know nothing about airflow or celery: an airflow worker runs each one, so
retries, logs and concurrency are the DAG's business, not this module's. The expensive per-process
resources (the fastembed model, the OpenSearch client) are built once per process by the cached
accessors below, which is what a celery Task base class used to do in __init__.

See dags/harvest_pipeline.py for how they are wired together.
"""

import datetime
import json
import logging
import os
from enum import Enum
from functools import lru_cache
from logging.config import dictConfig
from typing import Any

import psycopg
import xmltodict
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
from harvester import HarvesterSettings, run_harvest
from jsonschema.validators import validate
from lxml import etree as ET
from opensearchpy import OpenSearch
from opensearchpy.helpers import BulkIndexError, bulk
from psycopg.rows import dict_row

from config.logging_config import LOGGING_CONFIG
from config.opensearch_config import OpenSearchConfig
from config.postgres_config import PostgresConfig
from transform.warehouse_api import WAREHOUSE_API_URL
from utils import handle_xml, normalize_datacite_json
from utils.embedding_utils import (
    OpenSearchSourceWithEmbedding,
    SourceWithEmbeddingText,
    add_embeddings_to_source,
    get_embedding_text_from_fields,
    preprocess_batch,
)
from utils.queue_utils import HarvestEventQueue

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# OAI-PMH XML namespaces
OAI_RECORD = f'{handle_xml.OAI}:record'
OAI_METADATA = f'{handle_xml.OAI}:metadata'


def require_env(name: str) -> str:
    """Fail at import rather than halfway through a batch, the way the celery worker used to."""
    value = os.environ.get(name)
    if not value:
        raise ValueError(f'Missing {name} environment variable')
    return value


EMBEDDING_MODEL = require_env('EMBEDDING_MODEL')

# The datacite JSON schema every normalized record is validated against, next to the config package
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'schema.json')


class ProviderCode(str, Enum):
    DANS = 'DANS'
    ZENODO = 'ZENODO'
    HAL = 'HAL'
    DABAR = 'DABAR'
    SWISSUBASE = 'SWISS'


@lru_cache(maxsize=1)
def file_db_config() -> PostgresConfig:
    """filedb, where the per record file metadata goes."""
    # TODO: how to configure DB and not hard code?
    return PostgresConfig(db=os.environ.get('FILE_DB'))


@lru_cache(maxsize=1)
def dataset_db_config() -> PostgresConfig:
    """datasetdb, the harvested records and their normalized datacite JSON."""
    return PostgresConfig()


@lru_cache(maxsize=1)
def opensearch_client() -> OpenSearch:
    opensearch_config = OpenSearchConfig()
    return OpenSearch(
        hosts=[{'host': opensearch_config.host, 'port': opensearch_config.port}],
        http_auth=None,
        use_ssl=False,
        logger=logger,
    )


@lru_cache(maxsize=1)
def embedding_transformer() -> TextEmbedding:
    """Loads the fastembed model, which is why this is cached per process and not per call.

    FASTEMBED_CACHE_DIR is read here rather than at import so a caller can point it at a writable
    directory before the first embedding: the airflow user cannot write the /root default.
    """
    cache_dir = os.environ.get('FASTEMBED_CACHE_DIR', '/root/.cache/fastembed')
    logger.info(f'Setting up embedding transformer with model {EMBEDDING_MODEL} (cache {cache_dir})')
    return TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=cache_dir)


@lru_cache(maxsize=1)
def datacite_schema() -> dict[Any, Any]:
    with open(SCHEMA_PATH) as f:
        schema: dict[Any, Any] = json.load(f)
    return schema


def parse_checksum(file: FileEntry | ZipEntry) -> tuple[str | None, str | None]:
    if not file.checksum:
        return None, None

    algo = file.checksum[0][0].replace('sha1', 'sha-1').upper()
    value = file.checksum[0][1]
    return algo, value


def make_file_entry(harvest_event: HarvestEventQueue, file: FileEntry) -> tuple[Any, ...]:
    checksum_type, checksum_value = parse_checksum(file)

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


def make_zip_entry(harvest_event: HarvestEventQueue, zip_file: ZipEntry) -> tuple[Any, ...]:
    checksum_type, checksum_value = parse_checksum(zip_file)

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


def collect_files(harvest_event: HarvestEventQueue, dataset: Dataset) -> list[tuple[Any, ...]]:
    return [make_file_entry(harvest_event, file) for file in dataset.crawl_file()]


def collect_crawled_files(harvest_event: HarvestEventQueue, dataset: Dataset) -> list[tuple[Any, ...]]:
    """Entries of a dataset crawled without a file listing, which is how swissubase is resolved.

    crawl() yields zips, plain files and directories; a DirEntry carries none of the checksum and
    version fields an entry needs, so it is skipped rather than crashing the batch.
    """
    entries: list[tuple[Any, ...]] = []
    for entry in dataset.crawl():
        if isinstance(entry, ZipEntry):
            entries.append(make_zip_entry(harvest_event, entry))
        elif isinstance(entry, FileEntry):
            entries.append(make_file_entry(harvest_event, entry))
    return entries


def harvest_endpoint(harvest_url: str) -> bool:
    """Harvest one OAI-PMH endpoint, writing its records through the warehouse API.

    The crawler is a library now (metadata-crawlers, imported as `harvester`), so this runs in the
    airflow task process instead of `docker compose run --rm harvester`. It reaches datasetdb the
    same way the container did, over the transform API, so the harvest_run bookkeeping and the
    additional-metadata fetching stay where they already are.

    Returns whether the harvest was complete, and does not raise on an incomplete one. run_harvest
    reports False for a single rejected record as readily as for an endpoint it never reached (it
    returns `failed_events == 0`), and feeds do repeat a record identifier, which the warehouse
    rejects with a 409. Failing the task on that would cost the whole pipeline: the sensor below it
    is NONE_FAILED, so one quirky endpoint out of 28 would block transforming the other 27.

    The outcome is recorded where it belongs instead: harvest_runs.status in datasetdb, this
    task's return value, and the errors the harvester logs above. Nothing was harvested is handled
    downstream too, where plan_transform_batches skips a run with no events.
    """
    logger.info(f'harvesting {harvest_url} through {WAREHOUSE_API_URL}')
    settings = HarvesterSettings(
        WAREHOUSE_API_URL=WAREHOUSE_API_URL,
        WAREHOUSE_API_TIMEOUT=int(os.environ.get('HARVEST_API_TIMEOUT') or 30),
    )
    # setup_logs=False: airflow captures this process's logging, a second file handler would only
    # write into the container filesystem where nobody reads it
    complete = run_harvest(harvest_url, settings=settings, setup_logs=False)
    if complete:
        logger.info(f'harvested {harvest_url}')
    else:
        logger.warning(f'{harvest_url}: harvest incomplete, see the errors above and harvest_runs.status')
    return complete


def add_file_metadata(batch: list[HarvestEventQueue]) -> int:
    """Resolve the files behind each record of the batch and write them to filedb."""
    success = 0

    with psycopg.connect(**file_db_config().connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        for harvest_event in batch:
            files = []

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

                files.extend(collect_files(harvest_event, ds_dv))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.ZENODO:
                # get id from DOI: 10.5281/zenodo.570959 -> 570959
                ds_z = ZenodoJsonSrcDataset(
                    harvest_event.record_identifier.split('.')[-1], harvest_event.additional_metadata
                )

                files.extend(collect_files(harvest_event, ds_z))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.HAL:
                # HAL IDs contain a version suffix, needs to be removed
                ds_hal = HalJsonSrcDataset(
                    harvest_event.record_identifier.split('v')[0], harvest_event.additional_metadata
                )

                files.extend(collect_files(harvest_event, ds_hal))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.DABAR:
                ds_dabar = DabarXmlSrcDataset('', harvest_event.additional_metadata)

                files.extend(collect_files(harvest_event, ds_dabar))

            elif harvest_event.code == ProviderCode.SWISSUBASE:
                ds_swiss = resolve(
                    f'https://www.swissubase.ch/en/catalogue/studies/1223/latest/datasets/114/{harvest_event.record_identifier}/overview'
                )

                files.extend(collect_crawled_files(harvest_event, ds_swiss))

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


def transform_batch(batch: list[HarvestEventQueue], index_name: str, *, reuse_embeddings: bool = False) -> Any:
    """Normalize, embed and index one batch of harvest events into OpenSearch and datasetdb."""
    client = opensearch_client()
    if not client.indices.exists(index=index_name):
        raise ValueError(f'Index {index_name} does not exist in OpenSearch')

    # transform to JSON and normalize
    # Error handling: if an error is thrown, psycopg will roll back the whole transaction and the whole batch fails because the exception is re-raised,
    # making sure that only the whole batch is synced with PostgreSQL. See https://www.psycopg.org/psycopg3/docs/basic/transactions.html:
    with psycopg.connect(**dataset_db_config().connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        normalized: list[SourceWithEmbeddingText] = []
        for harvest_event in batch:
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
                        client.delete(
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
                validate(instance=normalized_record, schema=datacite_schema())
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
                src_with_emb = add_embeddings_to_source(normalized, embedding_transformer())
                logger.info(f'Calculated embeddings for {len(src_with_emb)}')
            preprocessed = preprocess_batch([src_with_emb_ele.src for src_with_emb_ele in src_with_emb], index_name)
        except Exception as e:
            logger.error(f'Could not calculate embeddings: {e}')
            raise e

        try:
            success, failed = bulk(client, preprocessed)
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
                doi = rec.src.get('doi')
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
                    DO UPDATE SET
                        resource_type = EXCLUDED.resource_type,
                        title = EXCLUDED.title,
                        raw_metadata = EXCLUDED.raw_metadata,
                        doi = EXCLUDED.doi,
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
                        doi,
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
