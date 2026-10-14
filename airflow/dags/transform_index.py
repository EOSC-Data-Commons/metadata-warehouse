"""Transform and index the harvest events of one (closed) harvest run.

Replaces the FastAPI route `/index` and the Celery task `transform_batch`:

    plan_batches  ->  run_batch (one mapped task per batch)  ->  summarize

* `plan_batches` checks the index and the run and splits the run into batches. It returns only small batch
  descriptors (first/last event id), never the records themselves.
* `run_batch` runs on the Airflow worker for the queue "transform" (one task at a time), in the transform venv
  of the image (dependencies from the repo's uv.lock, see docker/airflow/Dockerfile). In one process it loads its
  batch from PostgreSQL and runs the unchanged transform logic (`transform.transform_core.transform_batch_impl`).
  State, retries and logs of every batch are part of Airflow.
"""

import os
from datetime import timedelta
from typing import Any

from airflow.sdk import Param, dag, get_current_context, task

DEFAULT_INDEX_NAME = os.environ.get('INDEX_NAME', 'test_datacite')
DEFAULT_BATCH_SIZE = int(os.environ.get('CELERY_BATCH_SIZE', '250'))

TRANSFORM_PYTHON = '/opt/airflow/transform-venv/bin/python'


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

    # Queue "transform" is consumed by airflow-worker-transform (concurrency 1, embedding model, keys.env).
    # Retrying is safe: records are upserted and deletes of missing records are no-ops.
    #
    # The function is executed in the transform venv, which has no Airflow: the source of the function is run there.
    # So everything it needs has to be imported inside it, and annotations must only use builtins
    # (they are evaluated there; `dict[str, Any]` would fail because `Any` is not imported in that process).
    @task.external_python(
        python=TRANSFORM_PYTHON,
        expect_airflow=False,
        expect_pendulum=False,
        queue='transform',
        retries=2,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(hours=1),
    )
    def run_transform_batch(batch: dict) -> int:
        import logging
        import time

        from planning.transform_planning import load_batch
        from transform.transform_core import TransformResources, transform_batch_impl

        # this process has no Airflow logging: send the logs of the transform code to the console (= task log)
        logging.basicConfig(level=logging.INFO, format='%(levelname)s %(asctime)s %(name)s@%(lineno)d %(message)s')

        events = load_batch(batch['harvest_run_id'], batch['first_id'], batch['last_id'])
        print(f'Loaded {len(events)} of {batch["size"]} planned events ({batch["first_id"]} .. {batch["last_id"]})')

        # loading the embedding model takes time on every task (fresh process): log it to be able to tune the batch size
        started = time.monotonic()
        resources = TransformResources()
        print(f'Transform resources ready after {time.monotonic() - started:.1f}s')

        started = time.monotonic()
        indexed = transform_batch_impl(resources, events, batch['index_name'], batch['reuse_embeddings'])

        print(f'Transformed batch in {time.monotonic() - started:.1f}s, {indexed} documents indexed')
        return indexed

    @task.external_python(
        python=TRANSFORM_PYTHON,
        expect_airflow=False,
        expect_pendulum=False,
        queue='filemeta',
        retries=2,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(hours=1),
    )
    def run_filemeta_batch(batch: dict) -> int:
        import logging
        import time
        from transform.file_meta_core import TransformFilemetadata, transform_filemetadata_batch_impl
        from planning.transform_planning import load_batch

        # this process has no Airflow logging: send the logs of the transform code to the console (= task log)
        logging.basicConfig(level=logging.INFO, format='%(levelname)s %(asctime)s %(name)s@%(lineno)d %(message)s')

        events = load_batch(batch['harvest_run_id'], batch['first_id'], batch['last_id'])
        print(f'Loaded {len(events)} of {batch["size"]} planned events ({batch["first_id"]} .. {batch["last_id"]})')

        files = TransformFilemetadata()
        started = time.monotonic()

        file_meta = transform_filemetadata_batch_impl(files, events)
        print(f'Transformed batch in {time.monotonic() - started:.1f}s, {file_meta} documents indexed')
        return file_meta

    @task
    def summarize(indexed: list[int]) -> None:
        print(f'Indexed {sum(indexed)} documents in {len(indexed)} batches')

    planned_batches = plan_batches()
    summarize(run_transform_batch.expand(batch=planned_batches))
    summarize(run_filemeta_batch.expand(batch=planned_batches))


transform_index()
