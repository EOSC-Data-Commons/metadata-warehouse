from datetime import datetime, timezone
from json import JSONDecodeError
from logging.config import dictConfig
from typing import Optional
import pgsql  # type: ignore
from config.logging_config import LOGGING_CONFIG
from config.postgres_config import PostgresConfig
from utils.queue_utils import HarvestEventQueue
from tasks import transform_batch
import os
from fastapi import FastAPI, Query, HTTPException
import logging
from pydantic import BaseModel
import json

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
        'description': 'Transformation and index process'
    },
    {
        'name': 'config',
        'description': 'Get available endpoints'
    },
    {
        'name': 'harvest_events',
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

class HarvestParams(BaseModel):
    metadata_prefix: str
    set: Optional[str]

class EndpointConfig(BaseModel):
    name: str
    harvest_url: str
    harvest_params: HarvestParams
    code: str
    suffix: str
    protocol: str
    last_harvest_date: Optional[datetime]


class Config(BaseModel):
    endpoints_configs: list[EndpointConfig]

class HarvestEvent(BaseModel):
    record_identifier: str
    raw_metadata: str
    additional_metadata: Optional[str] = None
    harvest_url: str
    repo_code: str

def create_harvest_event_in_db(harvest_event: HarvestEvent) -> None:
    """
    Creates a record in table harvest_events

    :param harvest_event: The new record to be created.
    :return:
    """

    with pgsql.Connection((postgres_config.address, postgres_config.port), postgres_config.user,
                          postgres_config.password,
                          tls=False) as db:

        db. execute(f"""
         INSERT INTO harvest_events 
                (record_identifier, 
                raw_metadata, 
                repository_id, 
                endpoint_id, 
                action, 
                metadata_protocol,
                metadata_format
                ) 
            VALUES ( 
                '{harvest_event.record_identifier}', 
                XMLPARSE(DOCUMENT '{harvest_event.raw_metadata.replace("'", "''")}'), 
                (SELECT id from repositories WHERE code='{harvest_event.repo_code}'),
                 (SELECT id from endpoints WHERE harvest_url='{harvest_event.harvest_url}'), 
                 'create', 
                 'OAI-PMH',
                  'XML');
        """)



def get_config_from_db() -> list[EndpointConfig]:
    """
    Returns the config for the available endpoints.
    """
    endpoints: list[EndpointConfig] = []

    try:
        with pgsql.Connection((postgres_config.address, postgres_config.port), postgres_config.user,
                              postgres_config.password,
                              tls=False) as db:

            with db.prepare(f"""
                SELECT endpoints.name, endpoints.harvest_url, endpoints.harvest_params, endpoints.code as suffix, endpoints.protocol, endpoints.last_harvest_date, repositories.code
    FROM endpoints, repositories
    WHERE endpoints.repository_id = repositories.id
            """) as docs:
                for doc in docs():

                    harvest_params = json.loads(doc.harvest_params)

                    endpoints.append(
                        EndpointConfig(name=doc.name, harvest_url=doc.harvest_url, code=doc.code, protocol=doc.protocol,
                                       harvest_params=HarvestParams(metadata_prefix=harvest_params.get('metadata_prefix'), set=harvest_params.get('set')), suffix=doc.suffix,
                                       last_harvest_date=doc.last_harvest_date))

        return endpoints
    except JSONDecodeError as e:
        logger.exception(f'Parsing of harvest_params failed: {e}')
        raise HTTPException(status_code=500, detail='Reading config failed.')
    except Exception as e:
        logger.exception(f'An error occurred when reading config: {e}')
        raise HTTPException(status_code=500, detail=str(e))


def create_jobs(index_name: str) -> int:
    """
    Creates and enqueues transformation jobs from harvest_events table.

    :param index_name: OpenSearch index to write resulting JSON files to.
    :return: Number of batches scheduled for processing.
    """

    batch: list[HarvestEventQueue] = []
    tasks = 0
    offset = 0
    limit = int(BATCH_SIZE) if BATCH_SIZE else 250
    fetch = True

    logger.info(f'Preparing jobs')
    with pgsql.Connection((postgres_config.address, postgres_config.port), postgres_config.user,
                          postgres_config.password,
                          tls=False) as db:
        # print(db)

        while fetch:

            with db.prepare(f"""
            SELECT ID, 
            repository_id, 
            endpoint_id, 
            record_identifier, 
            (
                xpath('/oai:record', raw_metadata, '{{{{oai, http://www.openarchives.org/OAI/2.0/}},{{datacite, http://datacite.org/schema/kernel-4}}}}')
            )[1] AS record
        FROM harvest_events
            ORDER BY ID
            LIMIT {limit}
            OFFSET {offset}
            """) as docs:

                for doc in docs():
                    batch.append(
                        HarvestEventQueue(id=doc.id, xml=doc.record, repository_id=doc.repository_id,
                                          endpoint_id=doc.endpoint_id, record_identifier=doc.record_identifier)
                    )

                if len(batch) == 0:
                    # batch is empty
                    break

            # https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#keeping-results
            logger.info(f'Putting batch of {len(batch)} in queue with offset {offset}')
            transform_batch.delay(batch, index_name)
            tasks += 1

            # increment offset by limit
            offset += limit
            # will be false if query returned fewer results than limit
            fetch = len(batch) == limit
            #fetch = False
            batch = []

    return tasks

@app.get('/index', tags=['index'])
def init_index(index_name: str = Query(default='test_datacite', description='Name of the OpenSearch index')) -> Index:
    # this long-running method is synchronous and runs in an external threadpool, see https://fastapi.tiangolo.com/async/#path-operation-functions
    # this way, it does not block the server
    try:
        results = create_jobs(index_name)
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
