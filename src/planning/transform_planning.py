"""Planning of the transformation jobs of a harvest run (used by the Airflow DAGs).

This replaces `create_jobs_in_queue` of the FastAPI app: the run is first split into batch ranges
(`plan_transform_batches`, tiny result). Each range is later loaded (`load_batch`) by its own Airflow task,
which transforms it.
"""

import logging

import psycopg
from opensearchpy import OpenSearch
from psycopg.rows import dict_row

from config.opensearch_config import OpenSearchConfig
from config.postgres_config import PostgresConfig
from planning.batching import BatchRange, chunk_ranges
from utils.queue_utils import HarvestEventQueue, detect_identifier_type

logger = logging.getLogger(__name__)

# number of ids fetched per round trip while planning
_PLAN_FETCH_SIZE = 10_000


def ensure_index_exists(index_name: str) -> None:
    opensearch_config = OpenSearchConfig()
    client = OpenSearch(
        hosts=[{'host': opensearch_config.host, 'port': opensearch_config.port}],
        http_auth=None,
        use_ssl=False,
        logger=logger,
    )
    try:
        if not client.indices.exists(index=index_name):
            raise ValueError(f'Index {index_name} does not exist in OpenSearch')
    finally:
        client.close()


def plan_transform_batches(harvest_run_id: str, batch_size: int) -> list[BatchRange]:
    """Splits the harvest events of a closed harvest run into batches of `batch_size` events."""
    with psycopg.connect(**PostgresConfig().connection_params, row_factory=dict_row) as conn:
        run = conn.execute('SELECT status FROM harvest_runs WHERE id = %s::uuid', (harvest_run_id,)).fetchone()
        if run is None:
            raise ValueError(f'Harvest run {harvest_run_id} does not exist')
        if run['status'] != 'closed':
            raise ValueError(f"Harvest run {harvest_run_id} has status '{run['status']}', only closed runs are indexed")

        # Only the ids are read: server-side cursor + index (harvest_run_id, id) keep this cheap for big runs.
        with conn.cursor(name='plan_harvest_events', row_factory=dict_row) as cur:
            cur.itersize = _PLAN_FETCH_SIZE
            cur.execute(
                'SELECT he.id FROM harvest_events he WHERE he.harvest_run_id = %s::uuid ORDER BY he.id',
                (harvest_run_id,),
            )
            return chunk_ranges((str(row['id']) for row in cur), batch_size)


def load_batch(harvest_run_id: str, first_id: str, last_id: str) -> list[HarvestEventQueue]:
    """Loads the harvest events of one planned batch (all events of the run with id in [first_id, last_id])."""
    with psycopg.connect(**PostgresConfig().connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT he.id,
            he.repository_id,
            r.code,
            he.endpoint_id,
            e.harvest_url,
            he.record_identifier,
            (
                xpath('/oai:record', he.raw_metadata, '{{oai, http://www.openarchives.org/OAI/2.0/},{datacite, http://datacite.org/schema/kernel-4}}')
            )[1] AS record,
            he.additional_metadata,
            he.is_deleted,
            he.datestamp,
            e.harvest_params
        FROM harvest_events he
        JOIN harvest_runs hr ON he.harvest_run_id = hr.id
        JOIN endpoints e ON he.endpoint_id = e.id
        JOIN repositories r ON he.repository_id = r.id
            WHERE he.harvest_run_id = %s::uuid AND hr.status = 'closed'
            AND he.id BETWEEN %s::uuid AND %s::uuid
            ORDER BY he.id
            """,
            (harvest_run_id, first_id, last_id),
        )

        batch: list[HarvestEventQueue] = []
        for doc in cur:
            harvest_params = doc.get('harvest_params') or {}
            additional_metadata_params = harvest_params.get('additional_metadata_params', {})

            batch.append(
                HarvestEventQueue(
                    id=str(doc['id']),
                    xml=doc['record'],
                    repository_id=str(doc['repository_id']),
                    endpoint_id=str(doc['endpoint_id']),
                    record_identifier=doc['record_identifier'],
                    identifier_type=detect_identifier_type(doc['record_identifier']),
                    code=doc['code'],
                    harvest_url=doc['harvest_url'],
                    additional_metadata=doc['additional_metadata'],
                    additional_metadata_API=additional_metadata_params.get('endpoint'),
                    additional_metadata_protocol=additional_metadata_params.get('protocol'),
                    is_deleted=doc['is_deleted'],
                    datestamp=doc['datestamp'].strftime('%Y-%m-%d %H:%M:%S.%f%z'),
                )
            )

    return batch
