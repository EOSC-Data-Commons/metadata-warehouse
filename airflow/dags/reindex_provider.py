"""Reindex all closed harvest runs of one provider (endpoint), strictly one after the other, oldest first.

Like `warehouse_harvest_and_index` with `all_runs=true`, but for one endpoint and without harvesting:

    plan_reindex  ->  index_runs

* `plan_reindex` checks the endpoint (unknown harvest url: the DAG run fails) and lists its closed runs, oldest first.
* `index_runs` is one task with a plain loop: for every run it triggers the DAG `warehouse_transform_index` through the
  Airflow REST API and waits until that run has finished, then it continues with the next run. If a run fails (or
  does not finish in time) the task fails and the later runs are NOT indexed, so a later run is never applied before
  an earlier one. The task has no retries (a retry would trigger a run that may already exist again): to continue
  after a failure trigger this DAG again, it starts from the oldest run (everything is idempotent).
* Why not TriggerDagRunOperator: in Airflow 3 its `execute()` cannot be called inside a task (the task runner does the
  triggering after the task function has ended), and mapped tasks do not guarantee order or stop at a failure.
* `index_types` selects what is run for every harvest run: the transform (OpenSearch), the file metadata or both.

Needs these environment variables in the worker (see x-airflow-warehouse-env in docker-compose.yml):
AIRFLOW_ADMIN_USER, AIRFLOW_ADMIN_PASSWORD and optionally AIRFLOW_API_URL (default: http://airflow-api-server:8080).
"""

import os
import time
from datetime import timedelta
from typing import Any

from airflow.sdk import Param, dag, get_current_context, task

DEFAULT_INDEX_NAME = os.environ.get('INDEX_NAME', 'test_datacite')
DEFAULT_BATCH_SIZE = int(os.environ.get('CELERY_BATCH_SIZE', '250'))

INDEX_TYPES = ['transform', 'filemeta']

TRANSFORM_DAG_ID = 'warehouse_transform_index'
POLL_INTERVAL_SECONDS = 30
# maximum time to wait for one run of warehouse_transform_index
RUN_TIMEOUT_SECONDS = 24 * 60 * 60
# consecutive failed status requests that are tolerated while waiting for a run (e.g. API server restart)
MAX_POLL_ERRORS = 5


def _api(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """Call the Airflow REST API (v2). A new token is requested for every call, so long chains cannot expire."""
    import requests

    base_url = os.environ.get('AIRFLOW_API_URL', 'http://airflow-api-server:8080')
    try:
        credentials = {'username': os.environ['AIRFLOW_ADMIN_USER'], 'password': os.environ['AIRFLOW_ADMIN_PASSWORD']}
    except KeyError as e:
        raise RuntimeError(f'Environment variable {e} is not set in the worker') from e

    token = requests.post(f'{base_url}/auth/token', json=credentials, timeout=30)
    token.raise_for_status()

    response = requests.request(
        method,
        f'{base_url}/api/v2{path}',
        headers={'Authorization': f'Bearer {token.json()["access_token"]}'},
        timeout=60,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]


def _wait_for_run(dag_run_id: str) -> str:
    """Wait until the run has finished, returns its final state ('success' or 'failed')."""
    import requests

    started = time.monotonic()
    errors = 0
    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            state = _api('GET', f'/dags/{TRANSFORM_DAG_ID}/dagRuns/{dag_run_id}')['state']
            errors = 0
        except requests.RequestException as e:
            errors += 1
            print(f'Could not get the state of {dag_run_id} ({errors}/{MAX_POLL_ERRORS}): {e}')
            if errors >= MAX_POLL_ERRORS:
                raise
            continue

        if state in ('success', 'failed'):
            return str(state)
        if time.monotonic() - started > RUN_TIMEOUT_SECONDS:
            raise TimeoutError(f'{dag_run_id} did not finish within {RUN_TIMEOUT_SECONDS // 3600}h (state: {state})')


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

    # No retries: a retry would start again from the first run and trigger runs that may already exist.
    @task(retries=0, execution_timeout=timedelta(days=14))
    def index_runs(run_confs: list[dict[str, Any]]) -> None:
        if not run_confs:
            print('Nothing to index')
            return

        # DAGs are created paused (DAGS_ARE_PAUSED_AT_CREATION): a run of a paused DAG would stay queued forever
        if _api('GET', f'/dags/{TRANSFORM_DAG_ID}')['is_paused']:
            raise RuntimeError(f'The DAG {TRANSFORM_DAG_ID} is paused, unpause it first')

        for position, conf in enumerate(run_confs, start=1):
            run = _api('POST', f'/dags/{TRANSFORM_DAG_ID}/dagRuns', json={'logical_date': None, 'conf': conf})
            dag_run_id = run['dag_run_id']
            print(f'[{position}/{len(run_confs)}] harvest run {conf["harvest_run_id"]}: triggered {dag_run_id}')

            # transform_index has max_active_runs=1: if another run is active, ours waits (queued) until it is done
            state = _wait_for_run(dag_run_id)
            if state != 'success':
                raise RuntimeError(
                    f'{dag_run_id} (harvest run {conf["harvest_run_id"]}) ended in state {state}. Stopping: '
                    f'{len(run_confs) - position} later runs were not indexed.'
                )
            print(f'[{position}/{len(run_confs)}] harvest run {conf["harvest_run_id"]}: success')

    index_runs(plan_reindex())


reindex_provider()
