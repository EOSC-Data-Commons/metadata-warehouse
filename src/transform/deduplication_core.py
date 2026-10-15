"""Deduplication of records.

If the same record (same url) exists several times, e.g. harvested from two endpoints, the record of the preferred
provider is kept and the others are deleted. Independent of Airflow: called by the DAG `deduplicate`.
"""

import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

from config.postgres_config import PostgresConfig
from utils.deduplication_utils import pick_winner

logger = logging.getLogger(__name__)

DEDUP_JOB_LOCK_KEY = 727001
BATCH_SIZE = 500


def merge_duplicate_group(conn: psycopg.Connection[dict[str, Any]], record_ids: list[Any]) -> int:
    """Keeps the preferred record of a group of duplicates and deletes the others.

    :return: number of deleted records (0 if the group was already resolved)
    """
    with conn.transaction():
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, e.harvest_url, repos.code, r.datacite_json
            FROM records r
            join endpoints e on endpoint_id = e.id
            join repositories repos on e.repository_id = repos.id
            WHERE r.id = ANY(%s)
            ORDER BY id
            FOR UPDATE
            """,
            (record_ids,),
        )
        rows = cur.fetchall()
        if len(rows) < 2:
            logger.info('Group %s already resolved, skipping', record_ids)
            return 0

        winner = pick_winner(rows)  # PROVIDER_PRECEDENCE
        loser_ids = [r['id'] for r in rows if r['id'] != winner['id']]

        cur.execute('DELETE FROM records WHERE id = ANY(%s)', (loser_ids,))
        logger.info('Merged group %s: kept %s, removed %s', record_ids, winner['id'], loser_ids)
        return len(loser_ids)


def _merge_all_groups(connection_params: dict[str, Any]) -> dict[str, int]:
    groups_found = 0
    groups_merged = 0
    records_removed = 0

    # autocommit: the lookups are single statements, every merge runs in its own transaction (conn.transaction())
    with psycopg.connect(**connection_params, row_factory=dict_row, autocommit=True) as conn:
        cursor_url = ''
        while True:
            batch = conn.execute(
                """
                SELECT url, array_agg(id ORDER BY id) AS ids
                FROM records
                WHERE url > %s
                GROUP BY url
                HAVING COUNT(*) > 1
                ORDER BY url
                LIMIT %s
                """,
                (cursor_url, BATCH_SIZE),
            ).fetchall()
            if not batch:
                break

            for row in batch:
                groups_found += 1
                removed = merge_duplicate_group(conn, row['ids'])
                if removed:
                    groups_merged += 1
                    records_removed += removed

            cursor_url = batch[-1]['url']
            if len(batch) < BATCH_SIZE:
                break

    return {
        'skipped': 0,
        'groups_found': groups_found,
        'groups_merged': groups_merged,
        'records_removed': records_removed,
    }


def deduplicate_records() -> dict[str, int]:
    """Finds all urls with more than one record and merges each group.

    A session level advisory lock on a separate connection makes sure only one deduplication runs at a time.
    It is held until all groups are merged.

    :return: statistics; 'skipped' is 1 if another deduplication is already running
    """
    connection_params = PostgresConfig().connection_params

    with psycopg.connect(**connection_params, row_factory=dict_row, autocommit=True) as lock_conn:
        lock = lock_conn.execute('SELECT pg_try_advisory_lock(%s) AS locked', (DEDUP_JOB_LOCK_KEY,)).fetchone()
        if not lock or not lock['locked']:
            logger.info('Deduplication job already running, skipping this invocation')
            return {'skipped': 1, 'groups_found': 0, 'groups_merged': 0, 'records_removed': 0}

        try:
            return _merge_all_groups(connection_params)
        finally:
            lock_conn.execute('SELECT pg_advisory_unlock(%s)', (DEDUP_JOB_LOCK_KEY,))
