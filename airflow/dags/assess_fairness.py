import json
import logging
from datetime import timedelta

import pendulum
from airflow.sdk import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook


logger = logging.getLogger(__name__)

POSTGRES_CONN_ID = 'datasetdb'
BATCH_SIZE = 100


def process_record(record_id: str, datacite_json: dict) -> None:
    """
    Process the DataCite metadata for a single record.

    Replace this implementation with your processing logic.
    """
    doi = datacite_json.get('doi')
    logger.info('Processing record %s, DOI: %s', record_id, doi)

    # TODO: Process datacite_json
    # e.g. enrich metadata, validate, index or transform


@dag(
    dag_id='process_datacite_records',
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['fair'],
)
def process_datacite_records():

    @task(
        retries=0,
        execution_timeout=timedelta(hours=2),
    )
    def process_records():
        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)

        conn = hook.get_conn()
        processed = 0

        try:
            # Server-side cursor avoids fetching all rows at once.
            with conn.cursor(name='records_cursor') as cursor:
                cursor.execute("""
                    SELECT id, datacite_json
                    FROM public.records
                    WHERE datacite_json IS NOT NULL
                """)

                while True:
                    records = cursor.fetchmany(BATCH_SIZE)

                    if not records:
                        break

                    logger.info(
                        'Fetched batch of %d records',
                        len(records),
                    )

                    for record_id, datacite_json in records:
                        parsed_datacite_json = (
                            json.loads(datacite_json) if isinstance(datacite_json, str) else datacite_json
                        )

                        process_record(record_id, parsed_datacite_json)
                        processed += 1

                    logger.info(
                        'Processed %d records so far',
                        processed,
                    )
        finally:
            conn.close()

        logger.info('Completed processing %d records', processed)

    process_records()


process_datacite_records()
