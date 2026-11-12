"""Reindex all closed harvest runs of one provider (endpoint), oldest first.

Like `warehouse_harvest_and_index` with `all_runs=true`, but for one endpoint and without harvesting:

    plan_reindex  ->  index_run (triggers the DAG `warehouse_transform_index` for each run, one at a time)

* The endpoint is identified by its harvest url. An unknown harvest url fails the DAG run.
* The runs are indexed sequentially, oldest first, so that the DB and the index end up in the state of the most
  recent run (later runs can update or delete what earlier runs harvested).
* `index_types` selects what is run for every harvest run: the transform (OpenSearch), the file metadata or both.
* If an `index_run` fails, the later runs are still indexed (mapped tasks are independent). Everything is idempotent:
  trigger this DAG again to index all runs from the oldest one again and to end up in the correct final state.
"""

import os
from datetime import timedelta
from typing import Any

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import Param, dag, get_current_context, task

DEFAULT_INDEX_NAME = os.environ.get('INDEX_NAME', 'test_datacite')
DEFAULT_BATCH_SIZE = int(os.environ.get('CELERY_BATCH_SIZE', '250'))

INDEX_TYPES = ['transform', 'filemeta']


@dag(
    dag_id='warehouse_reindex_provider',
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['warehouse'],
    params={
        'harvest_url': Param(type='string', minLength=1, description='Harvest url of the endpoint to reindex'),
        'index_types': Param(
            INDEX_TYPES,
            type='array',
            items={'type': 'string', 'enum': INDEX_TYPES},
            minItems=1,
            uniqueItems=True,
            examples=INDEX_TYPES,
            description='Which indexing to run: transform (OpenSearch), filemeta (file DB) or both',
        ),
        'index_name': Param(DEFAULT_INDEX_NAME, type='string', description='Target OpenSearch index'),
        'reuse_embeddings': Param(False, type='boolean', description='Reuse embeddings stored in the DB'),
        'batch_size': Param(DEFAULT_BATCH_SIZE, type='integer', minimum=1, description='Harvest events per batch'),
    },
)
def reindex_provider() -> None:
    @task(retries=0)
    def plan_reindex() -> list[dict[str, Any]]:
        from planning.harvest_planning import endpoint_exists, find_closed_runs

        params = get_current_context()['params']
        harvest_url = params['harvest_url']

        if not endpoint_exists(harvest_url):
            raise ValueError(f'No endpoint with harvest url {harvest_url}')

        # oldest first (ordered by completion time)
        runs = find_closed_runs([harvest_url], None)
        print(f'{len(runs)} closed runs of {harvest_url} to index with {params["index_types"]}')

        return [
            {
                'harvest_run_id': run['harvest_run_id'],
                'index_types': params['index_types'],
                'index_name': params['index_name'],
                'reuse_embeddings': params['reuse_embeddings'],
                'batch_size': params['batch_size'],
            }
            for run in runs
        ]

    runs_to_index = plan_reindex()

    # The DAG transform_index (max_active_runs=1) indexes one run; wait for it, then continue with the next run.
    TriggerDagRunOperator.partial(
        task_id='index_run',
        trigger_dag_id='warehouse_transform_index',
        wait_for_completion=True,
        poke_interval=60,
        max_active_tis_per_dag=1,
        allowed_states=['success'],
        failed_states=['failed'],
        retries=0,
        execution_timeout=timedelta(days=1),
    ).expand(conf=runs_to_index)


reindex_provider()
