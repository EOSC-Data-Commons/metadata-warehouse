from datetime import datetime, timezone
from typing import Optional

import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg import errors as psycopg_errors
from psycopg.rows import dict_row

from api_classes import (
    Config,
    HarvestEventCreateRequest,
    HarvestEventCreateResponse,
    HarvestRunCloseRequest,
    HarvestRunCloseResponse,
    HarvestRunCreateRequest,
    HarvestRunCreateResponse,
    HarvestRunGetResponse,
    HealthGetResponse,
    IndexGetResponse,
    SchedulerClosedRunsResponse,
    SchedulerRunsResponse,
)
from db_methods import (
    are_all_runs_closed_in_db,
    close_harvest_run_in_db,
    connection_params,
    create_harvest_events_bulk_in_db,
    create_harvest_run_in_db,
    create_jobs_in_queue,
    get_config_from_db,
    get_latest_harvest_run_in_db,
)
from setup_logger import logger

tags_metadata = [
    {'name': 'health', 'description': 'Health route'},
    {
        'name': 'index',
        'description': 'Start transformation and indexing process for a given harvest run',
    },
    {'name': 'config', 'description': 'Get available endpoints'},
    {'name': 'harvest_run', 'description': 'Manage harvest runs'},
    {'name': 'harvest_event', 'description': 'Register one or multiple harvest event'},
]

app = FastAPI(openapi_tags=tags_metadata)


@app.get('/index', tags=['index'])
def init_index(
    harvest_run_id: str = Query(default=None, description='Id of the harvest run to be indexed'),
    index_name: str = Query(default=None, description='Name of the OpenSearch index to use for indexing'),
) -> IndexGetResponse:
    # this long-running method is synchronous and runs in an external threadpool, see https://fastapi.tiangolo.com/async/#path-operation-functions
    # this way, it does not block the server
    try:
        results = create_jobs_in_queue(harvest_run_id, index_name)
    except Exception as e:
        logger.exception('Indexing failed')
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f'Got results: {results}')
    return IndexGetResponse(number_of_batches=results)


@app.get('/health', tags=['health'], summary='Get health status')
def get_health() -> HealthGetResponse:
    logger.info('health route called')
    return HealthGetResponse(status='ok', time=datetime.now(timezone.utc))


@app.get('/config', tags=['config'], summary='Get configs of available endpoints')
def get_config() -> Config:
    try:
        return Config(endpoints_configs=get_config_from_db())
    except Exception as e:
        logger.exception('Indexing failed')
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/harvest_event', tags=['harvest_event'], summary='Register a new harvest event')
def create_harvest_event(
    harvest_event: HarvestEventCreateRequest,
) -> HarvestEventCreateResponse:
    try:
        # logger.debug(harvest_event)
        return create_harvest_events_bulk_in_db([harvest_event])[0]
    except psycopg_errors.UniqueViolation as e:
        logger.exception(f'Harvest event could not be created for given harvest run')
        raise HTTPException(
            status_code=409,
            detail='Harvest event could not be created for the given harvest run because the record identifier already exists.',
        )
    except Exception as e:
        logger.exception(f'An error occurred when creating harvest event: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/harvest_event_bulk', tags=['harvest_event'], summary='Register multiple harvest events in one transaction')
def create_harvest_events_bulk(
    harvest_events: list[HarvestEventCreateRequest],
) -> list[HarvestEventCreateResponse]:
    try:
        return create_harvest_events_bulk_in_db(harvest_events)
    except psycopg_errors.UniqueViolation as e:
        logger.exception(f'Harvest events could not be created for given harvest run')
        raise HTTPException(
            status_code=409,
            detail='One or more harvest events could not be created because the record identifier already exists.',
        )
    except Exception as e:
        logger.exception(f'An error occurred when creating harvest events: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    '/harvest_run',
    tags=['harvest_run'],
    summary='Get latest harvest runs',
    description="""
Optional filters:
- only_active → return only active endpoints
- respect_schedule → return only endpoints that should be harvested now
""",
)
def get_harvest_run(
    harvest_url: Optional[str] = Query(default=None, description='harvest url of the endpoint'),
    only_active: bool = Query(default=False, description='Return only active endpoints'),
    respect_schedule: bool = Query(
        default=False,
        description='Return only endpoints that should be harvested now based on harvest_schedule',
    ),
) -> HarvestRunGetResponse:
    try:
        return get_latest_harvest_run_in_db(
            harvest_url=harvest_url,
            only_active=only_active,
            respect_schedule=respect_schedule,
        )

    except Exception as e:
        logger.exception('Error getting harvest run')
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    '/harvest_run',
    tags=['harvest_run'],
    summary='Create a new havest run for a given endpoint.',
    description='A new harvest run can only be created if no other open harvest run exists for the same endpoint.',
)
def create_harvest_run(
    harvest_run: HarvestRunCreateRequest,
) -> HarvestRunCreateResponse:
    try:
        logger.debug(harvest_run)
        return create_harvest_run_in_db(harvest_run.harvest_url)
    except psycopg_errors.UniqueViolation as e:
        logger.exception(f'An open harvest run already exists for the given endpoint.')
        raise HTTPException(
            status_code=400,
            detail='An open harvest run already exists for the given endpoint.',
        )
    except Exception as e:
        logger.exception(f'An error occurred when creating harvest event: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@app.put(
    '/harvest_run',
    tags=['harvest_run'],
    summary='Close an open harvest run for a given endpoint.',
)
def close_harvest_run(harvest_run: HarvestRunCloseRequest) -> HarvestRunCloseResponse:
    try:
        return close_harvest_run_in_db(harvest_run)
    except Exception as e:
        logger.exception(f'An error occurred when closing harvest event: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    '/scheduler/wait-for-completion',
    tags=['scheduler'],
    summary='Check if all harvest runs are closed',
)
def scheduler_wait_for_completion() -> SchedulerRunsResponse:
    """
    Determine whether Crawler has finished its work
    and Scheduler can trigger Transfomer.

    The scheduler periodically checks whether all harvest runs
    have finished execution.

    A run is considered finished when its status is:
    - 'closed'  -> completed successfully
    - 'failed'  -> completed with errors but no longer running

    Only runs with status='open' block the scheduler.

    Returns
    -------
    SchedulerRunsResponse
        Object containing boolean flag:

        all_closed=True
            no open runs exist → scheduler may proceed

        all_closed=False
            at least one run is still open → scheduler should wait
    """
    try:
        all_closed = are_all_runs_closed_in_db()

        return SchedulerRunsResponse(all_closed=all_closed)

    except Exception as e:
        logger.exception('Scheduler completion check failed')

        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    '/scheduler/closed-runs',
    tags=['scheduler'],
    summary='Return closed or failed harvest runs completed in the last 6 days',
)
def get_closed_runs(
    all_runs: bool = Query(False, description='If true, return runs from any time, not just the last 6 days'),
) -> SchedulerClosedRunsResponse:
    """
    Retrieve IDs of recently finished harvest runs.

    This endpoint returns harvest runs that are no longer active,
    meaning their status is:
    - 'closed'
    - 'failed'

    By default, results are limited to runs completed within the last 6 days
    to avoid reprocessing older runs and to keep Transformer payloads small.

    Parameters
    ----------
    all_runs : bool, optional
        If True, the 6-day recency filter is disabled and all matching runs
        are returned regardless of age. Defaults to False.

    Returns
    -------
    SchedulerClosedRunsResponse
        harvest_run_ids : list[str]
            IDs of runs eligible for further processing.

    Notes
    -----
    Expected status values in harvest_runs table:
        ('open', 'closed', 'failed')

    Filtering logic:
        status IN ('closed', 'failed')
        AND (all_runs=True OR until_date >= NOW() - INTERVAL '6 days')
    """
    try:
        with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT id
                FROM harvest_runs
                WHERE status IN ('closed', 'failed')
                AND (%(all_runs)s OR until_date >= NOW() - INTERVAL '6 days')
            """,
                {'all_runs': all_runs},
            )

            ids = [str(row['id']) for row in cur.fetchall()]

        return SchedulerClosedRunsResponse(harvest_run_ids=ids)

    except Exception as e:
        logger.exception('Failed to fetch closed runs')
        raise HTTPException(status_code=500, detail=str(e))
