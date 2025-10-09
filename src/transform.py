from datetime import datetime, timezone
from logging.config import dictConfig
import pgsql  # type: ignore
from fastapi.concurrency import run_in_threadpool
from config.logging_config import LOGGING_CONFIG
from config.postgres_config import PostgresConfig
from utils.queue_utils import HarvestEvent
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
        'description': 'Transformation and index process'
    }
]

app = FastAPI(openapi_tags=tags_metadata)
postgres_config: PostgresConfig = PostgresConfig()

class Health(BaseModel):
    status: str
    time: datetime

class Index(BaseModel):
    number_of_batches: int

def create_jobs(index_name: str) -> int:
    batch: list[HarvestEvent] = []
    tasks = 0
    offset = 0
    limit = int(BATCH_SIZE) if BATCH_SIZE else 250
    fetch = True

    logger.info(f'Preparing jobs')
    with pgsql.Connection((postgres_config.address, postgres_config.port), postgres_config.user, postgres_config.password,
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
                        HarvestEvent(id=doc.id, xml=doc.record, repository_id=doc.repository_id,
                                     endpoint_id=doc.endpoint_id, record_identifier=doc.record_identifier)
                    )

            # https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#keeping-results
            logger.info(f'Putting batch of {len(batch)} in queue with offset {offset}')
            transform_batch.delay(batch, index_name)
            tasks = tasks + 1

            # increment offset by limit
            offset = offset + limit
            # will be false if query returned fewer results than limit
            fetch = len(batch) == limit
            #fetch = False
            batch = []

    return tasks


@app.get('/index', tags = ['index'])
async def index(index_name: str = Query(default='test_datacite', description='Name of the OpenSearch index')) -> Index:
    try:
        # https://www.starlette.io/threadpool/
        results = await run_in_threadpool(
            create_jobs, index_name
        )

    except Exception as e:
        logger.exception("Indexing failed")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f'Got results: {results}')
    return Index(number_of_batches=results)


@app.get('/health', tags=['health'])
async def health() -> Health:
    logger.info('health route called')
    return Health(status = 'ok', time=datetime.now(timezone.utc))
