from datetime import datetime, timezone
from json import JSONDecodeError
from logging.config import dictConfig
from typing import Optional
import psycopg
from psycopg.rows import dict_row
from config.logging_config import LOGGING_CONFIG
from config.postgres_config import PostgresConfig
from utils.queue_utils import HarvestEventQueue
from tasks import transform_batch
import os
from fastapi import FastAPI, Query, HTTPException
import logging
from pydantic import BaseModel

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

BATCH_SIZE = os.environ.get('CELERY_BATCH_SIZE')
if not BATCH_SIZE or not BATCH_SIZE.isnumeric():
    raise ValueError('Missing or invalid CELERY_BATCH_SIZE environment variable')

tags_metadata = [
    {
        'name': 'health',
        'description': 'Health route'
    },
    {
        'name': 'index',
        'description': 'Start transformation and index process'
    },
    {
        'name': 'config',
        'description': 'Get available endpoints'
    },
    {
        'name': 'harvest_run',
        'description': 'Create a harvest run'
    },
    {
        'name': 'harvest_event',
        'description': 'Create a harvest event'
    }
]

app = FastAPI(openapi_tags=tags_metadata)
postgres_config: PostgresConfig = PostgresConfig()


class Health(BaseModel):
    status: str
    time: datetime


class Index(BaseModel):
    number_of_batches: int

class AdditionalMetadataParams(BaseModel):
    format: str
    endpoint: str
    protocol: str

class HarvestParams(BaseModel):
    metadata_prefix: str
    set: Optional[list[str]]
    additional_metadata_params: Optional[AdditionalMetadataParams]

class EndpointConfig(BaseModel):
    name: str
    harvest_url: str
    harvest_params: HarvestParams
    code: str
    protocol: str


class Config(BaseModel):
    endpoints_configs: list[EndpointConfig]


class HarvestEvent(BaseModel):
    record_identifier: str
    raw_metadata: str # XML
    additional_metadata: Optional[str] = None # XML or JSON (stringified)
    harvest_url: str
    repo_code: str
    harvest_run_id: str
    is_deleted: bool

class HarvestRunBase(BaseModel):
    pass

class HarvestRunCreateRequest(HarvestRunBase):
    harvest_url: str

class HarvestRunGetResponse(BaseModel):
    id: Optional[str]

class HarvestRunCreateResponse(HarvestRunBase):
    id: str
    from_date: Optional[datetime]
    until_date: datetime
    endpoint_config: EndpointConfig

class HarvestRunCloseRequest(HarvestRunBase):
    id: str
    success: bool
    started_at: datetime
    completed_at: datetime

class HarvestRunCloseResponse(HarvestRunBase):
    pass

def get_open_harvest_run_in_db(harvest_url: str) -> HarvestRunGetResponse:
    with psycopg.connect(dbname=postgres_config.user, user=postgres_config.user, host=postgres_config.address, password=postgres_config.password, port=postgres_config.port, row_factory=dict_row) as conn:

        cur = conn.cursor()

        cur.execute("""
            SELECT hr.id 
     FROM harvest_runs hr
     JOIN endpoints e ON hr.endpoint_id = e.id
     WHERE e.harvest_url = %s AND hr.status = 'open' 
     LIMIT 1
        """, [harvest_url])

        open_harvest_run = cur.fetchone()

        if open_harvest_run is not None:
            return HarvestRunGetResponse(id=str(open_harvest_run['id']))
        else:
            return HarvestRunGetResponse(id=None)

def create_harvest_run_in_db(harvest_url: str) -> HarvestRunCreateResponse:
    """
    Creates a new entry in harvest_runs and returns its id.

    :param harvest_url: The new entry to be created.
    """

    with psycopg.connect(dbname=postgres_config.user, user=postgres_config.user, host=postgres_config.address, password=postgres_config.password, port=postgres_config.port, row_factory=dict_row) as conn:

        cur = conn.cursor()
        # TODO: only allow one open harvest run per endpoint
        # TODO check (in one transaction):
        # - an open harvest run exists for the given endpoint
        # - only create a new harvest run if all previous are closed, if any

        # https://stackoverflow.com/questions/15710162/conditional-insert-into-statement-in-postgres/15710289
        res = cur.execute("""
            INSERT INTO harvest_runs
                (endpoint_id, status, from_date)
                select 
                (SELECT id FROM endpoints WHERE harvest_url = %s),
                'open',
                (SELECT until_date 
     FROM harvest_runs hr
     JOIN endpoints e ON hr.endpoint_id = e.id
     WHERE e.harvest_url = %s 
       AND hr.status = 'closed' 
     ORDER BY hr.started_at DESC 
     LIMIT 1)
            """, (harvest_url, harvest_url))

        logger.debug(f'insert operation state: {res}')

        cur.execute("""SELECT hr.id, hr.from_date, hr.until_date,  e.name, e.harvest_url, e.harvest_params, e.protocol, r.code  
                    FROM harvest_runs hr
                    JOIN endpoints e ON hr.endpoint_id = e.id
                    JOIN repositories r ON e.repository_id = r.id
                    WHERE hr.status = 'open' and e.harvest_url = %s""", [harvest_url])
        new_harvest_run = cur.fetchone()

        if new_harvest_run is None:
            raise Exception(f'Harvest run could not be created')

        logger.debug(f'{new_harvest_run}')

        return HarvestRunCreateResponse(
            id=str(new_harvest_run['id']),
            from_date=new_harvest_run['from_date'],
            until_date=new_harvest_run['until_date'],
            endpoint_config=EndpointConfig(name=new_harvest_run['name'], harvest_url=new_harvest_run['harvest_url'], code=new_harvest_run['code'], protocol=new_harvest_run['protocol'],
                                   harvest_params=HarvestParams(metadata_prefix=new_harvest_run['harvest_params'].get('metadata_prefix'), set=new_harvest_run['harvest_params'].get('set'), additional_metadata_params=new_harvest_run['harvest_params'].get('additional_metadata_params')))
        )


def close_harvest_run_in_db(harvest_run: HarvestRunCloseRequest) -> None:
    with psycopg.connect(dbname=postgres_config.user, user=postgres_config.user, host=postgres_config.address,
                         password=postgres_config.password, port=postgres_config.port, row_factory=dict_row) as conn:

        cur = conn.cursor()

        state = 'closed' if harvest_run.success else 'failed'

        cur.execute("""
            UPDATE harvest_runs
            SET status = %s, started_at = %s, completed_at = %s 
            WHERE id = %s and status = 'open'
        """, (state, harvest_run.started_at, harvest_run.completed_at, harvest_run.id))


def create_harvest_event_in_db(harvest_event: HarvestEvent) -> None:
    """
    Creates a record in table harvest_events

    :param harvest_event: The new record to be created.
    """

    with psycopg.connect(dbname=postgres_config.user, user=postgres_config.user, host=postgres_config.address, password=postgres_config.password, port=postgres_config.port, row_factory=dict_row) as conn:

        cur = conn.cursor()

        cur.execute("""
                        INSERT INTO harvest_events 
                            (record_identifier, 
                            raw_metadata,
                            additional_metadata,
                            repository_id, 
                            endpoint_id, 
                            action, 
                            metadata_protocol,
                            metadata_format,
                            harvest_run_id,
                            is_deleted
                            ) 
                        VALUES ( 
                            %s, 
                            XMLPARSE(DOCUMENT %s), 
                            %s,
                            (SELECT id from repositories WHERE code=%s),
                            (SELECT id from endpoints WHERE harvest_url=%s), 
                            %s, 
                            %s,
                            %s,
                            (SELECT id FROM harvest_runs WHERE id = %s and status = 'open'),
                            %s
                            );
                        """, (harvest_event.record_identifier, harvest_event.raw_metadata, harvest_event.additional_metadata, harvest_event.repo_code, harvest_event.harvest_url, 'create', 'OAI-PMH', 'XML', harvest_event.harvest_run_id, harvest_event.is_deleted))


def get_config_from_db() -> list[EndpointConfig]:
    """
    Returns the config for the available endpoints.
    """
    endpoints: list[EndpointConfig] = []

    try:
        with psycopg.connect(dbname=postgres_config.user, user=postgres_config.user, host=postgres_config.address,
                             password=postgres_config.password, port=postgres_config.port,
                             row_factory=dict_row) as conn:

            cur = conn.cursor()

            cur.execute("""
SELECT 
    e.name, 
    e.harvest_url, 
    e.harvest_params, 
    e.protocol, 
    r.code
FROM endpoints e
JOIN repositories r ON e.repository_id = r.id
            """)
            for doc in cur.fetchall():

                endpoints.append(
                    EndpointConfig(name=doc['name'], harvest_url=doc['harvest_url'], code=doc['code'], protocol=doc['protocol'],
                                   harvest_params=HarvestParams(metadata_prefix=doc['harvest_params'].get('metadata_prefix'), set=doc['harvest_params'].get('set'), additional_metadata_params=doc['harvest_params'].get('additional_metadata_params'))))

        return endpoints
    except JSONDecodeError as e:
        logger.exception(f'Parsing of harvest_params failed: {e}')
        raise HTTPException(status_code=500, detail='Reading config failed.')
    except Exception as e:
        logger.exception(f'An error occurred when reading config: {e}')
        raise HTTPException(status_code=500, detail=str(e))


def create_jobs_in_queue(harvest_run_id: str) -> int:
    """
    Creates and enqueues transformation jobs from harvest_events table.

    :param harvest_run_id: ID of the harvest run the harvest events belong to..
    :return: Number of batches scheduled for processing.
    """

    batch: list[HarvestEventQueue] = []
    tasks = 0
    offset = 0
    limit = int(BATCH_SIZE) if BATCH_SIZE else 250
    fetch = True

    logger.info(f'Preparing jobs')

    with psycopg.connect(dbname=postgres_config.user, user=postgres_config.user, host=postgres_config.address, password=postgres_config.password, port=postgres_config.port, row_factory=dict_row) as conn:

        cur = conn.cursor()

        # print(db)

        while fetch:

            cur.execute("""
            SELECT he.id, 
            he.repository_id,
            r.code, 
            he.endpoint_id, 
            e.harvest_url,
            he.record_identifier, 
            (
                xpath('/oai:record', he.raw_metadata, '{{oai, http://www.openarchives.org/OAI/2.0/},{datacite, http://datacite.org/schema/kernel-4}}')
            )[1] AS record,
            he.additional_metadata,
            he.is_deleted
        FROM harvest_events he
        JOIN harvest_runs hr ON he.harvest_run_id = hr.id 
        JOIN endpoints e ON he.endpoint_id = e.id
        JOIN repositories r ON he.repository_id = r.id
            WHERE harvest_run_id = %s and hr.status = 'closed' 
            ORDER BY he.id
            LIMIT %s
            OFFSET %s
            """, (harvest_run_id, limit, offset))

            for doc in cur.fetchall():

                # https://www.psycopg.org/psycopg3/docs/basic/adapt.html#uuid-adaptation
                # https://docs.python.org/3/library/uuid.html#uuid.UUID
                # str(uuid) returns a string in the form 12345678-1234-5678-1234-567812345678 where the 32 hexadecimal digits represent the UUID.
                batch.append(
                    HarvestEventQueue(id=str(doc['id']), xml=doc['record'], repository_id=str(doc['repository_id']),
                                 endpoint_id=str(doc['endpoint_id']), record_identifier=doc['record_identifier'], code=doc['code'], harvest_url=doc['harvest_url'], additional_metadata=doc['additional_metadata'], is_deleted=doc['is_deleted'])
                )

            if len(batch) == 0:
                # batch is empty
                break

            # https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#keeping-results
            logger.info(f'Putting batch of {len(batch)} in queue with offset {offset}')
            transform_batch.delay(batch, 'test_datacite')
            tasks += 1

            # increment offset by limit
            offset += limit
            # will be false if query returned fewer results than limit
            fetch = len(batch) == limit
            #fetch = False
            batch = []

    return tasks

@app.get('/index', tags=['index'])
def init_index(harvest_run_id: str = Query(default=None, description='Id of the harvest run to be indexed')) -> Index:
    # this long-running method is synchronous and runs in an external threadpool, see https://fastapi.tiangolo.com/async/#path-operation-functions
    # this way, it does not block the server
    try:
        results = create_jobs_in_queue(harvest_run_id)
    except Exception as e:
        logger.exception("Indexing failed")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f'Got results: {results}')
    return Index(number_of_batches=results)


@app.get('/health', tags=['health'])
def get_health() -> Health:
    logger.info('health route called')
    return Health(status='ok', time=datetime.now(timezone.utc))


@app.get('/config', tags=['config'])
def get_config() -> Config:
    try:
        return Config(endpoints_configs=get_config_from_db())
    except Exception as e:
        logger.exception("Indexing failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/harvest_event', tags=['harvest_event'])
def create_harvest_event(harvest_event: HarvestEvent) -> None:
    try:
        logger.debug(harvest_event)
        create_harvest_event_in_db(harvest_event)
    except Exception as e:
        logger.exception(f'An error occurred when creating harvest event: {e}')
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/harvest_run', tags=['harvest_run'])
def get_harvest_run(harvest_url: str = Query(default=None, description='Name of the OpenSearch index')) -> HarvestRunGetResponse:
    try:
        return get_open_harvest_run_in_db(harvest_url)
    except Exception as e:
        logger.exception(f'An error occurred when creating harvest event: {e}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/harvest_run', tags=['harvest_run'])
def create_harvest_run(harvest_run: HarvestRunCreateRequest) -> HarvestRunCreateResponse:
    try:
        logger.debug(harvest_run)
        return create_harvest_run_in_db(harvest_run.harvest_url)
    except Exception as e:
        logger.exception(f'An error occurred when creating harvest event: {e}')
        raise HTTPException(status_code=500, detail=str(e))

@app.put('/harvest_run', tags=['harvest_run'])
def close_harvest_run(harvest_run: HarvestRunCloseRequest) -> None:
    try:
        return close_harvest_run_in_db(harvest_run)
    except Exception as e:
        logger.exception(f'An error occurred when creating harvest event: {e}')
        raise HTTPException(status_code=500, detail=str(e))

