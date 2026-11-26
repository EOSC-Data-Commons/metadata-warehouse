"""Check if the file DB can be looked up for the records of the dataset DB. Read-only, trigger manually.

    plan_endpoints  ->  check_endpoint (one mapped task per endpoint)  ->  report

The file metadata of a record is found in the file DB by (harvest_url, record_identifier), the dataset DB only knows the
`endpoint_id` of a record. For every endpoint the task `check_endpoint` goes through its records, translates the
endpoint to its harvest url and counts the matching rows of `record_files`. A record that has `additional_metadata` but
no file rows is a possible sync issue (for a provider that the file extractor supports). The details and the buckets
are described in `planning/file_sync_check.py`. The report is written to the log of the task `report`.
"""

import os
from datetime import timedelta
from typing import Any

from airflow.sdk import Param, dag, get_current_context, task

DEFAULT_BATCH_SIZE = int(os.environ.get('CHECK_BATCH_SIZE', '1000'))


@dag(
    dag_id='warehouse_check_file_sync',
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['warehouse'],
    params={
        'harvest_urls': Param(
            [],
            type='array',
            items={'type': 'string', 'minLength': 1},
            uniqueItems=True,
            description='Check only these endpoints (empty: all endpoints)',
        ),
        'only_gaps': Param(False, type='boolean', description='Report only endpoints with possible sync issues'),
        'sample_size': Param(
            10, type='integer', minimum=0, description='Examples of records with a possible sync issue per endpoint'
        ),
        'batch_size': Param(
            DEFAULT_BATCH_SIZE, type='integer', minimum=1, description='Records per lookup in the file DB'
        ),
        'fail_on_gaps': Param(False, type='boolean', description='Fail the DAG run if there are possible sync issues'),
    },
)
def check_file_sync() -> None:
    @task(retries=0)
    def plan_endpoints() -> list[dict[str, Any]]:
        from planning.file_sync_check import list_endpoints

        params = get_current_context()['params']

        endpoints = list_endpoints(list(params['harvest_urls']))
        print(f'{len(endpoints)} endpoints to check')

        return [
            {**endpoint, 'batch_size': params['batch_size'], 'sample_size': params['sample_size']}
            for endpoint in endpoints
        ]

    # Only reads, so retrying is safe.
    @task(retries=2, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(hours=6))
    def check_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
        from planning.file_sync_check import check_endpoint as check

        return check(endpoint, endpoint['batch_size'], endpoint['sample_size'])

    @task(retries=0)
    def report(results: list[dict[str, Any]]) -> None:
        from planning.file_sync_check import format_report, has_gaps

        params = get_current_context()['params']
        results = list(results)

        print(format_report(results, params['only_gaps']))

        with_gaps = [stats['harvest_url'] for stats in results if has_gaps(stats)]
        if params['fail_on_gaps'] and with_gaps:
            raise RuntimeError(f'Possible sync issues in {len(with_gaps)} endpoints: {", ".join(with_gaps)}')

    report(check_endpoint.expand(endpoint=plan_endpoints()))


check_file_sync()
