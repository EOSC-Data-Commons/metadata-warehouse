"""Harvest the endpoints that are due and index the harvested runs.

Replaces the custom scheduler (`python -m scheduler.run`):

    plan_endpoints
      -> harvest_independent (one mapped task per endpoint, one at a time)
      -> harvest_dependent   (endpoints that depend on another endpoint, e.g. Zenodo after HAL)
      -> plan_indexing       (closed runs created by this DAG run)
      -> index_run           (triggers the DAG `transform_index` for each run, one at a time)

* The harvester runs as a Python module (`harvester.run_harvest`) inside the Airflow worker, so its logs are part of
  the Airflow task log. A failed harvest fails only its own task; the other endpoints are still harvested and indexed.
* Nothing has to poll for "all runs closed": a harvest task only finishes when the crawler has closed its run.
* `max_active_runs=1` keeps two DAG runs from harvesting at the same time.

The schedule is taken from the environment variable HARVEST_SCHEDULE (cron expression, e.g. `0 2 * * *`);
without it the DAG only runs when triggered manually.
"""

import os
from datetime import timedelta
from typing import Any

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import Param, dag, get_current_context, task

DEFAULT_INDEX_NAME = os.environ.get('INDEX_NAME', 'test_datacite')
DEFAULT_BATCH_SIZE = int(os.environ.get('CELERY_BATCH_SIZE', '250'))

HARVEST_PYTHON = '/opt/airflow/harvester-venv/bin/python'


@dag(
    dag_id='harvest_and_index',
    schedule=os.environ.get('HARVEST_SCHEDULE') or None,
    catchup=False,
    max_active_runs=1,
    tags=['warehouse'],
    params={
        'harvest_urls': Param(
            [], type='array', items={'type': 'string'}, description='Harvest these endpoints instead of the due ones'
        ),
        'all_runs': Param(False, type='boolean', description='Index all closed runs, not only the ones harvested now'),
        'index_name': Param(DEFAULT_INDEX_NAME, type='string', description='Target OpenSearch index'),
        'reuse_embeddings': Param(False, type='boolean', description='Reuse embeddings stored in the DB'),
        'batch_size': Param(DEFAULT_BATCH_SIZE, type='integer', minimum=1, description='Harvest events per batch'),
    },
)
def harvest_and_index() -> None:
    @task(multiple_outputs=True, retries=0)
    def plan_endpoints() -> dict[str, Any]:
        from planning.harvest_planning import db_now_iso, get_endpoints_to_harvest

        params = get_current_context()['params']

        # Reference time from the DB: runs completed after it were harvested by this DAG run.
        since = db_now_iso()

        if params['harvest_urls']:
            independent, dependent = list(params['harvest_urls']), []
        else:
            independent, dependent = get_endpoints_to_harvest(os.environ['WAREHOUSE_API_URL'])

        print(f'{len(independent)} independent and {len(dependent)} dependent endpoints to harvest')
        return {'independent': independent, 'dependent': dependent, 'all_urls': independent + dependent, 'since': since}

    # `.expand()` needs the whole return value of a task, not one key of a multiple_outputs dict,
    # so these tiny tasks extract the two lists.
    @task
    def pick(plan: dict[str, Any], key: str) -> list[str]:
        return list(plan[key])

    # One endpoint at a time (like the old scheduler). No retries: a failed crawler leaves its run in a final state
    # ('failed'), a retry would open a new run for the same endpoint.
    @task.external_python(
        python=HARVEST_PYTHON,
        expect_airflow=False,
        expect_pendulum=False,
        retries=0,
        max_active_tis_per_dag=1,
    )
    def harvest(url: str) -> bool:
        import logging

        from harvester import HarvesterSettings, run_harvest

        # this process has no Airflow logging: send the logs of the transform code to the console (= task log)
        logging.basicConfig(level=logging.INFO, format='%(levelname)s %(asctime)s %(name)s@%(lineno)d %(message)s')

        settings = HarvesterSettings(
            WAREHOUSE_API_URL=os.environ['WAREHOUSE_API_URL'],
            LOG_DIR='/tmp/harvester-logs',  # only used if setup_logs=True
        )
        # setup_logs=False: keep Airflow's logging, so the crawler logs end up in the task log
        success = run_harvest(url, settings=settings, setup_logs=False)
        if not success:
            raise RuntimeError(f'Harvesting of {url} failed, see the log above')
        return True

    @task(trigger_rule='all_done', retries=0)
    def plan_indexing(urls: list[str], since: str) -> list[dict[str, Any]]:
        from planning.harvest_planning import find_closed_runs

        params = get_current_context()['params']

        if params['all_runs']:
            runs = find_closed_runs(None, None)
        else:
            runs = find_closed_runs(urls, since)

        print(f'{len(runs)} closed runs to index')
        return [
            {
                'harvest_run_id': run['harvest_run_id'],
                'index_name': params['index_name'],
                'reuse_embeddings': params['reuse_embeddings'],
                'batch_size': params['batch_size'],
            }
            for run in runs
        ]

    plan = plan_endpoints()
    independent_urls = pick.override(task_id='independent_urls')(plan, 'independent')
    dependent_urls = pick.override(task_id='dependent_urls')(plan, 'dependent')

    harvest_independent = harvest.override(task_id='harvest_independent').expand(url=independent_urls)
    # all_done: also runs if there was nothing to harvest before, or if an endpoint failed
    harvest_dependent = harvest.override(task_id='harvest_dependent', trigger_rule='all_done').expand(
        url=dependent_urls
    )
    harvest_independent >> harvest_dependent

    runs_to_index = plan_indexing(urls=plan['all_urls'], since=plan['since'])
    harvest_dependent >> runs_to_index

    # The DAG transform_index (max_active_runs=1) indexes one run; wait for it, then continue with the next run.
    TriggerDagRunOperator.partial(
        task_id='index_run',
        trigger_dag_id='transform_index',
        wait_for_completion=True,
        poke_interval=60,
        max_active_tis_per_dag=1,
        execution_timeout=timedelta(days=1),
    ).expand(conf=runs_to_index)


harvest_and_index()
