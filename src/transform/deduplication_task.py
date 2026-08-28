from typing import Any

import psycopg
from celery import Task
from psycopg.rows import dict_row

from config.postgres_config import PostgresConfig
from transform.celery_app_def import celery_app, logger

DEDUP_JOB_LOCK_KEY = 727001
BATCH_SIZE = 500


class FindDuplicatesTask(Task): # type: ignore
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        self.postgres_config = PostgresConfig()


@celery_app.task(base=FindDuplicatesTask, bind=True, ignore_result=True)
def find_duplicates(self: Any) -> Any:
    with psycopg.connect(**self.postgres_config.connection_params, row_factory=dict_row, autocommit=False) as conn:
        cur = conn.cursor()

        # Attempts to acquire a lock for this transaction and will be automatically released
        # See https://www.postgresql.org/docs/9.1/functions-admin.html
        cur.execute('SELECT pg_try_advisory_xact_lock(%s)', (DEDUP_JOB_LOCK_KEY,))
        lock_status = cur.fetchone()
        logger.debug(f'lock_status: {lock_status}')

        if not lock_status or not lock_status.get('pg_try_advisory_xact_lock'):
            logger.info('Deduplication job already running, skipping this invocation')
            return

        cursor_url = ''
        dispatched = 0
        while True:
            cur.execute(
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
            )
            batch = cur.fetchall()
            if not batch:
                break

            for row in batch:
                remove_duplicates.delay(row['ids'])
                dispatched += 1

            logger.info(batch)

            cursor_url = batch[-1]['url']
            if len(batch) < BATCH_SIZE:
                break

        logger.info(f'Dispatched {dispatched} deduplication merge tasks')


PROVIDER_PRECEDENCE: dict[str, dict[str, Any]] = {
    'ZENODO': {
        'rank': 10,
        'harvest_urls': [
            'https://zenodo.org/oai2d',
        ],
    },
    'DANS': {
        'rank': 20,
        'harvest_urls': [
            'https://phys-techsciences.datastations.nl/oai',  # preferred DANS endpoint
            'https://archaeology.datastations.nl/oai',  # fallback
        ],
    },
    'HAL': {
        'rank': 30,
        'harvest_urls': [
            'https://api.archives-ouvertes.fr/oai/hal',
        ],
    },
}

UNKNOWN_RANK = 999


class DeduplicationTask(Task): # type: ignore
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        self.postgres_config = PostgresConfig()

    @staticmethod
    def _precedence_key(row: dict[str, Any]) -> tuple[int, int]:
        code_entry = PROVIDER_PRECEDENCE.get(row['code'])
        if code_entry is None:
            return UNKNOWN_RANK, UNKNOWN_RANK

        code_rank = code_entry['rank']
        harvest_urls = code_entry.get('harvest_urls', [])
        try:
            url_rank = harvest_urls.index(row['harvest_url'])
        except ValueError:
            url_rank = len(harvest_urls)  # known code, unlisted url -> lowest priority within that code

        return code_rank, url_rank

    @staticmethod
    def pick_winner(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return min(rows, key=DeduplicationTask._precedence_key)


@celery_app.task(base=DeduplicationTask, bind=True, ignore_result=True)
def remove_duplicates(self: Any, record_ids: list[str]) -> Any:

    logger.info(f'Deduplicating {record_ids} records')

    with psycopg.connect(**self.postgres_config.connection_params, row_factory=dict_row) as conn:
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
                logger.info(f'Group {record_ids} already resolved, skipping')
                return

            logger.info(rows)

            winner = self.pick_winner(rows)  # PROVIDER_PRECEDENCE
            loser_ids = [r['id'] for r in rows if r['id'] != winner['id']]

            cur.execute('DELETE FROM records WHERE id = ANY(%s)', (loser_ids,))
            logger.info(f'Merged group {record_ids}: kept {winner["id"]}, removed {loser_ids}')
