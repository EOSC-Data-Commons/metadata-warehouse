"""Slicing a closed harvest run into the batches the DAG maps over.

Airflow's dynamic task mapping carries every mapped value through the metadata DB as an XCom, so
the DAG maps over slice descriptors (`harvest_run_id` plus the id to start at) and each mapped task
reads its own records with fetch_batch(). Sending the records themselves would push megabytes of
raw OAI-PMH XML per batch through XCom.

Slices are keyset ranges, not OFFSET windows: plan_batches() records the first harvest_events.id of
each batch and fetch_batch() reads forward from it, so every batch costs one index range scan
instead of scanning and sorting everything before it. Both order by harvest_events.id, so a given
descriptor always resolves to the same records, which is what makes a retry of one mapped task
reprocess exactly the batch that failed.
"""

import logging
import os
from typing import Any, TypedDict

import psycopg
from psycopg.rows import dict_row

from config.postgres_config import PostgresConfig
from utils.queue_utils import HarvestEventQueue, detect_identifier_type

logger = logging.getLogger(__name__)

BATCH_SIZE_DEFAULT = 125
try:
    BATCH_SIZE = int(os.environ.get('TRANSFORM_BATCH_SIZE') or BATCH_SIZE_DEFAULT)
except (TypeError, ValueError) as err:
    raise ValueError('TRANSFORM_BATCH_SIZE should be an integer') from err

# The first id of every batch, plus the run total so the plan can be logged. `%%` is a literal
# modulo, psycopg reads a single % as a placeholder.
#
# Not `hr.status = 'closed'`: the harvester closes a run as failed when a single record was
# rejected, and /scheduler/closed-runs hands the DAG closed and failed runs alike. Filtering on
# 'closed' here dropped every event of a run that had one duplicate record identifier.
_SELECT_BATCH_STARTS = """
    WITH numbered AS (
        SELECT he.id,
            row_number() OVER (ORDER BY he.id) AS position,
            count(*) OVER () AS total
        FROM harvest_events he
        JOIN harvest_runs hr ON he.harvest_run_id = hr.id
        WHERE he.harvest_run_id = %s AND hr.status <> 'open'
    )
    SELECT id, total
    FROM numbered
    WHERE (position - 1) %% %s = 0
    ORDER BY id
"""

# Columns fetch_batch selects, kept next to the row -> HarvestEventQueue mapping below
_SELECT_EVENTS = """
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
    WHERE he.harvest_run_id = %s AND hr.status <> 'open' AND he.id >= %s::uuid
    ORDER BY he.id
    LIMIT %s
"""


class BatchSlice(TypedDict):
    """One mapped task's share of a harvest run. JSON serializable, it travels as an XCom."""

    harvest_run_id: str
    start_id: str
    limit: int
    batch_number: int


def connection_params() -> dict[str, Any]:
    """datasetdb, where harvest_events and records live."""
    return PostgresConfig().connection_params


def plan_batches(harvest_run_ids: list[str], batch_size: int | None = None) -> list[BatchSlice]:
    """Split the given finished harvest runs into the slices to map transformation tasks over.

    Returns a flat list across all runs so the DAG can expand a single mapped task over it, rather
    than mapping per run and having to flatten mapped output. A run that is still open, or that
    harvested nothing, contributes no slices.
    """
    size = batch_size or BATCH_SIZE
    slices: list[BatchSlice] = []

    with psycopg.connect(**connection_params(), row_factory=dict_row) as conn:
        for harvest_run_id in harvest_run_ids:
            starts = conn.execute(_SELECT_BATCH_STARTS, (harvest_run_id, size)).fetchall()
            if not starts:
                logger.info(f'harvest run {harvest_run_id} has no events to transform')
                continue

            slices.extend(
                BatchSlice(
                    harvest_run_id=harvest_run_id,
                    start_id=str(row['id']),
                    limit=size,
                    batch_number=number,
                )
                for number, row in enumerate(starts, start=1)
            )
            logger.info(f'harvest run {harvest_run_id}: {starts[0]["total"]} events in {len(starts)} batches of {size}')

    return slices


def fetch_batch(harvest_run_id: str, start_id: str, limit: int, batch_number: int = 1) -> list[HarvestEventQueue]:
    """Read the harvest events of one slice, ready to hand to transform_batch/add_file_metadata."""
    events: list[HarvestEventQueue] = []

    with psycopg.connect(**connection_params(), row_factory=dict_row) as conn:
        cur = conn.execute(_SELECT_EVENTS, (harvest_run_id, start_id, limit))

        for doc in cur.fetchall():
            # https://www.psycopg.org/psycopg3/docs/basic/adapt.html#uuid-adaptation
            harvest_params = doc.get('harvest_params') or {}
            additional_metadata_params = harvest_params.get('additional_metadata_params') or {}

            events.append(
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

    logger.info(f'fetched {len(events)} events for run {harvest_run_id} (batch {batch_number})')
    return events
