"""The harvest -> transform pipeline, replacing the cron driven scheduler service.

    list_endpoints_to_harvest
        -> harvest_endpoint (mapped, one per endpoint)
        -> wait_for_runs_closed (sensor)
        -> list_closed_runs -> plan_transform_batches
        -> transform_batch / add_file_metadata (mapped, one per batch)

The jobs themselves are plain functions in transform.jobs, run by an airflow worker off the celery
queue. What used to be one celery task per batch is a mapped task per batch, so a batch that fails
retries on its own and its logs sit in the UI next to the batch that produced them.

Mapped tasks carry their arguments through XCom, so the transformation maps over slice descriptors
and each task reads its own records, see transform.batches.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from airflow.sdk import Param, TriggerRule, dag, get_current_context, task
from airflow.sdk.bases.sensor import PokeReturnValue
from airflow.sdk.exceptions import AirflowSkipException

from transform import batches, jobs, warehouse_api

# A batch embeds ~125 records on CPU
TRANSFORM_TIMEOUT = timedelta(hours=6)

# How long harvesting may take before the pipeline gives up waiting for the runs to close
HARVEST_TIMEOUT = timedelta(hours=48)
HARVEST_POKE_INTERVAL = timedelta(minutes=5)


def dag_params() -> dict[str, Any]:
    """The params of the running DAG, whether triggered manually or on schedule."""
    params: dict[str, Any] = get_current_context()['params']
    return params


@dag(
    dag_id='harvest_pipeline',
    description='Harvest the due OAI-PMH endpoints, transform their records, index them for search',
    # schedule='0 2 * * *',  # daily at 2am UTC, enable once the pipeline is trusted to run itself
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    # Two concurrent runs would write the same records of the same harvest runs
    max_active_runs=1,
    default_args={'retries': 2, 'retry_delay': timedelta(minutes=5)},
    params={
        'skip_harvest': Param(
            default=False,
            type='boolean',
            description='Skip harvesting and only transform the runs that are already closed. '
            'A plain trigger harvests every endpoint whose harvest_schedule has elapsed, so pin '
            'harvest_urls to keep a run small',
        ),
        'harvest_urls': Param(
            default=[],
            type='array',
            items={'type': 'string'},
            description='Harvest exactly these endpoints instead of the ones whose schedule has '
            'elapsed, e.g. one small repository for a smoke test of the whole pipeline',
        ),
        'all_runs': Param(
            default=False,
            type='boolean',
            description='Transform closed runs from any time, not just the last 6 days '
            '(the --all-runs flag of the old scheduler)',
        ),
        'index_name': Param(
            default='',
            type='string',
            description='OpenSearch index to write to. Empty uses the INDEX_NAME environment variable',
        ),
        'reuse_embeddings': Param(
            default=False,
            type='boolean',
            description='Reuse the embeddings already stored in datasetdb instead of recomputing them',
        ),
    },
    tags=['warehouse'],
)
def harvest_pipeline() -> None:
    @task
    def list_endpoints_to_harvest() -> list[str]:
        """Harvest URLs of the endpoints whose harvest_schedule has elapsed, or the pinned ones."""
        params = dag_params()
        if params['skip_harvest']:
            return []
        if pinned := params['harvest_urls']:
            return [str(url) for url in pinned]
        return warehouse_api.get_endpoints_to_harvest()

    @task(execution_timeout=HARVEST_TIMEOUT, map_index_template='{{ task.op_kwargs["harvest_url"] }}')
    def harvest_endpoint(harvest_url: str) -> bool:
        """Harvest one OAI-PMH endpoint into datasetdb, see transform.jobs.harvest_endpoint."""
        return jobs.harvest_endpoint(harvest_url)

    @task.sensor(
        poke_interval=int(HARVEST_POKE_INTERVAL.total_seconds()),
        timeout=int(HARVEST_TIMEOUT.total_seconds()),
        # frees the executor slot between pokes instead of holding a subprocess for hours
        mode='reschedule',
        # the transformation must run on whatever landed: skip_harvest skips the mapped task and a
        # single unreachable endpoint must not keep the other 27 repositories out of the warehouse
        trigger_rule=TriggerRule.ALL_DONE,
    )
    def wait_for_runs_closed() -> PokeReturnValue:
        """Block the transformation until no harvest run is still open."""
        return PokeReturnValue(is_done=warehouse_api.are_all_runs_closed())

    @task
    def list_closed_runs() -> list[str]:
        """Ids of the closed or failed harvest runs that still need transforming."""
        return warehouse_api.get_closed_run_ids(all_runs=dag_params()['all_runs'])

    @task
    def plan_transform_batches(harvest_run_ids: list[str]) -> list[batches.BatchSlice]:
        """Split those runs into the batches the two mapped tasks below each get one of."""
        slices = batches.plan_batches(harvest_run_ids)
        if not slices:
            raise AirflowSkipException('no harvest events to transform')
        return slices

    @task(
        execution_timeout=TRANSFORM_TIMEOUT,
        map_index_template='{{ task.op_kwargs["harvest_run_id"][:8] }}/{{ task.op_kwargs["batch_number"] }}',
    )
    def transform_batch(harvest_run_id: str, start_id: str, limit: int, batch_number: int) -> int:
        """Normalize, embed and index one batch into OpenSearch and datasetdb."""
        params = dag_params()
        index_name = params['index_name'] or os.environ['INDEX_NAME']
        batch = batches.fetch_batch(harvest_run_id, start_id, limit, batch_number)
        return int(jobs.transform_batch(batch, index_name, reuse_embeddings=params['reuse_embeddings']))

    @task(
        execution_timeout=TRANSFORM_TIMEOUT,
        map_index_template='{{ task.op_kwargs["harvest_run_id"][:8] }}/{{ task.op_kwargs["batch_number"] }}',
    )
    def add_file_metadata(harvest_run_id: str, start_id: str, limit: int, batch_number: int) -> int:
        """Resolve the files behind one batch of records and write them to filedb."""
        batch = batches.fetch_batch(harvest_run_id, start_id, limit, batch_number)
        return jobs.add_file_metadata(batch)

    harvested = harvest_endpoint.expand(harvest_url=list_endpoints_to_harvest())
    closed = wait_for_runs_closed()
    run_ids = list_closed_runs()
    # taskflow passes an XComArg where the function declares list[str], which mypy cannot model
    slices = plan_transform_batches(run_ids)  # type: ignore[arg-type]

    harvested >> closed >> run_ids

    transform_batch.expand_kwargs(slices)
    # filedb is independent: crawling external file APIs is slow and flaky, indexing must not wait
    add_file_metadata.expand_kwargs(slices)


harvest_pipeline()
