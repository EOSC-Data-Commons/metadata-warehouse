import logging
from datetime import timedelta

from airflow.sdk import dag, task, Param, get_current_context
from airflow.providers.postgres.hooks.postgres import PostgresHook
from fair_offline_assessor import FairAssessor

logger = logging.getLogger(__name__)

POSTGRES_CONN_ID = 'datasetdb'
BATCH_SIZE = 100
MAX_PARALLEL_BATCHES = 4


def process_record(record_id: str, xml: str) -> None:
    """
    Process the DataCite metadata for a single record.

    Replace this implementation with your processing logic.
    """
    logger.info(f'Processing record {record_id}')

    def _extract_fair_results(data: dict) -> dict:
        return data.get('summary', {})

    assessor = FairAssessor()
    full_result = assessor.assess(
        metadata=xml,
        metadata_format='xml',
    )
    summary = _extract_fair_results(full_result.model_dump())
    logger.info(summary)
    # TODO: write to database


@dag(
    dag_id='process_datacite_records',
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['fair'],
    params={
        'sample_size': Param(
            default=100,
            type='integer',
            minimum=1,
            title='Number of random records',
            description='Number of records to randomly select and process.',
        ),
    },
)
def process_datacite_records():

    @task
    def select_random_batches() -> list[list[str]]:
        sample_size = get_current_context()['params']['sample_size']

        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        conn = hook.get_conn()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id
                    FROM public.records
                    WHERE raw_metadata IS NOT NULL
                    ORDER BY random()
                    LIMIT %s
                    """,
                    (sample_size,),
                )

                batches = []

                while records := cursor.fetchmany(BATCH_SIZE):
                    batches.append([str(record_id) for (record_id,) in records])

                logger.info(
                    'Selected %d batches',
                    len(batches),
                )
                return batches
        finally:
            conn.close()

    @task(
        retries=0,
        execution_timeout=timedelta(hours=2),
        max_active_tis_per_dag=MAX_PARALLEL_BATCHES,
    )
    def process_batch(record_ids: list[str]):
        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        conn = hook.get_conn()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, raw_metadata
                    FROM public.records
                    WHERE id = ANY(%s)
                    """,
                    (record_ids,),
                )

                records = cursor.fetchall()

            for record_id, raw_metadata in records:
                process_record(record_id, raw_metadata)

            logger.info(
                'Processed batch of %d records',
                len(records),
            )
        finally:
            conn.close()

    process_batch.expand(record_ids=select_random_batches())


process_datacite_records()
