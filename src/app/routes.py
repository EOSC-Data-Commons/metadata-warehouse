from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from psycopg import errors as psycopg_errors

from app.api_classes import (
    Config,
    DependencyNotHarvestedError,
    HarvestEventCreateRequest,
    HarvestEventCreateResponse,
    HarvestRunCloseRequest,
    HarvestRunCloseResponse,
    HarvestRunCreateRequest,
    HarvestRunCreateResponse,
    HarvestRunGetResponse,
    HealthGetResponse,
    IndexGetResponse,
)
from app.db_methods import (
    close_harvest_run_in_db,
    create_harvest_events_bulk_in_db,
    create_harvest_run_in_db,
    get_config_from_db,
    get_latest_harvest_run_in_db,
)
from config.postgres_config import PostgresConfig
from logger.setup_logger import logger

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
postgres_config: PostgresConfig = PostgresConfig()
connection_params = postgres_config.connection_params


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
    except DependencyNotHarvestedError as e:
        logger.exception(f'An error occurred when creating harvest run: {e}')
        raise HTTPException(
            status_code=400,
            detail=f'This is a dependent repository and requires the endpoint {e.dependency} to be harvested first',
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
