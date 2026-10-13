"""Transform and index the harvest events of one (closed) harvest run.

Replaces the FastAPI route `/index` (the enqueuing/planning part):

    plan_batches  ->  run_batch (one mapped task per batch)  ->  summarize

* `plan_batches` checks the index and the run and splits the run into batches. It returns only small batch
  descriptors (first/last event id), never the records themselves.
* `run_batch` loads one batch from PostgreSQL, sends it to the existing Celery worker (task `transform_batch`,
  unchanged) and waits for the result. A failing Celery task fails the Airflow task, which is then retried.

Airflow only orchestrates: the heavy dependencies (fastembed, ...) stay in the Celery worker image.
"""

import os
from datetime import timedelta
from typing import Any

from airflow.sdk import Param, dag, get_current_context, task

DEFAULT_INDEX_NAME = os.environ.get('INDEX_NAME', 'test_datacite')
DEFAULT_BATCH_SIZE = int(os.environ.get('CELERY_BATCH_SIZE', '250'))

TRANSFORM_TASK_NAME = 'transform.transform_task.transform_batch'
# max. time to wait for the Celery worker to finish one batch (includes waiting in the queue)
BATCH_TIMEOUT = timedelta(hours=1)


@dag(
    dag_id='transform_index',
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['warehouse'],
    params={
        'harvest_run_id': Param(type='string', minLength=36, maxLength=36, description='ID of a closed harvest run'),
        'index_name': Param(DEFAULT_INDEX_NAME, type='string', description='Target OpenSearch index'),
        'reuse_embeddings': Param(False, type='boolean', description='Reuse embeddings stored in the DB'),
        'batch_size': Param(DEFAULT_BATCH_SIZE, type='integer', minimum=1, description='Harvest events per batch'),
    },
)
def transform_index() -> None:
    @task(retries=0)
    def plan_batches() -> list[dict[str, Any]]:
        from planning.transform_planning import ensure_index_exists, plan_transform_batches

        params = get_current_context()['params']
        harvest_run_id = params['harvest_run_id']

        ensure_index_exists(params['index_name'])
        ranges = plan_transform_batches(harvest_run_id, params['batch_size'])
        print(f'Harvest run {harvest_run_id}: {sum(r.size for r in ranges)} events in {len(ranges)} batches')

        return [
            {
                **r._asdict(),
                'harvest_run_id': harvest_run_id,
                'index_name': params['index_name'],
                'reuse_embeddings': params['reuse_embeddings'],
            }
            for r in ranges
        ]

    # The Celery worker processes one batch at a time (--concurrency=1). Two batches in flight keep it busy
    # without blocking all slots of the Airflow worker while they wait.
    # Retrying is safe: records are upserted and deletes of missing records are no-ops.
    @task(retries=2, retry_delay=timedelta(minutes=1), max_active_tis_per_dag=2, execution_timeout=BATCH_TIMEOUT)
    def run_batch(batch: dict[str, Any]) -> int:
        from celery import Celery
        from planning.transform_planning import load_batch

        events = load_batch(batch['harvest_run_id'], batch['first_id'], batch['last_id'])
        print(f'Loaded {len(events)} of {batch["size"]} planned events ({batch["first_id"]} .. {batch["last_id"]})')

        # Celery client for the same RabbitMQ that Airflow's executor uses. Broker and result backend have to match
        # the Celery app of the worker (src/transform/celery_app_def.py). The task is called by name, so the
        # `transform` package (and fastembed etc.) is not needed here.
        client = Celery(
            'airflow-client',
            broker=os.environ['AIRFLOW__CELERY__BROKER_URL'],
            backend=os.environ.get('CELERY_RESULT_BACKEND', 'rpc://'),
        )
        result = client.send_task(
            TRANSFORM_TASK_NAME,
            kwargs={'batch': events, 'index_name': batch['index_name'], 'reuse_embeddings': batch['reuse_embeddings']},
        )
        print(f'Sent Celery task {result.id}, waiting for the result')

        # re-raises the exception of the Celery task, if there was one
        indexed: int = result.get(timeout=BATCH_TIMEOUT.total_seconds(), disable_sync_subtasks=False)
        print(f'Celery task {result.id} finished, {indexed} documents indexed')
        return indexed

    @task
    def summarize(indexed: list[int]) -> None:
        print(f'Indexed {sum(indexed)} documents in {len(indexed)} batches')

    summarize(run_batch.expand(batch=plan_batches()))


transform_index()
