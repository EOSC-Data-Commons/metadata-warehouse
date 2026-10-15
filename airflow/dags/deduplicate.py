"""Deduplicate the records in the database.

Replaces the Celery tasks `find_duplicates` and `remove_duplicates` (and the route `POST /deduplicate`):
for every url that exists more than once the record of the preferred provider is kept, the others are deleted.

Trigger it manually, e.g. after `harvest_and_index` has finished. One task finds and merges all groups, so the lock
that prevents two deduplications from running at the same time covers the whole run.
"""

from datetime import timedelta

from airflow.sdk import dag, task

TRANSFORM_PYTHON = '/opt/airflow/transform-venv/bin/python'


@dag(
    dag_id='deduplicate',
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['warehouse'],
)
def deduplicate() -> None:
    # Runs in the transform venv (see docker/airflow/Dockerfile) on the default queue.
    # Everything the function needs has to be imported inside it, annotations may only use builtins.
    # Retrying is safe: groups that are already merged are skipped.
    @task.external_python(
        python=TRANSFORM_PYTHON,
        expect_airflow=False,
        expect_pendulum=False,
        retries=1,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(hours=2),
    )
    def run_deduplication() -> dict:
        import logging

        from transform.deduplication_core import deduplicate_records

        # this process has no Airflow logging: send the logs to the console (= task log)
        logging.basicConfig(level=logging.INFO, format='%(levelname)s %(asctime)s %(name)s@%(lineno)d %(message)s')

        stats = deduplicate_records()
        logging.getLogger('deduplicate').info('Deduplication finished: %s', stats)
        return stats

    run_deduplication()


deduplicate()
