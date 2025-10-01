from datetime import datetime
from logging.config import dictConfig
import pgsql # type: ignore
from fastapi.concurrency import run_in_threadpool
from config.logging_config import LOGGING_CONFIG
from config.postgres_config import PostgresConfig
from utils.queue_utils import XMLRecord
#import psycopg2
from tasks import transform_batch
import os
from fastapi import FastAPI
from typing import Any, NamedTuple
import logging


dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

BATCH_SIZE = os.environ.get('CELERY_BATCH_SIZE')
if not BATCH_SIZE or not BATCH_SIZE.isnumeric():
    raise ValueError('Missing or invalid CELERY_BATCH_SIZE environment variable')

app = FastAPI()
postgres_config: PostgresConfig = PostgresConfig()

def create_jobs(index_name: str) -> int:
    batch: list[XMLRecord] = []
    tasks = 0
    offset = 0
    limit = int(BATCH_SIZE) if BATCH_SIZE else 250
    fetch = True

    logger.info(f'Preparing jobs')
    with pgsql.Connection(('postgres', postgres_config.port), postgres_config.user, postgres_config.password, tls=False) as db:
        # print(db)

        while fetch:

            with db.prepare(f"""
            SELECT ID, (xpath('/oai:record', raw_metadata, '{{{{oai, http://www.openarchives.org/OAI/2.0/}},{{datacite, http://datacite.org/schema/kernel-4}}}}'))[1] AS root
        FROM harvest_events
            ORDER BY ID
            LIMIT {limit}
            OFFSET {offset}
            """) as docs:

                for doc in docs():
                    batch.append(XMLRecord(id=doc.id, xml=doc.root))

            # https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#keeping-results
            logger.info(f'Putting batch of {len(batch)} in queue with offset {offset}')
            transform_batch.delay(batch, index_name)
            tasks = tasks + 1

            # increment offset by limit
            offset = offset + limit
            # will be false if query returned fewer results than limit
            fetch = len(batch) == limit
            batch = []

    return tasks


@app.get("/index")
async def index(index_name: str) -> dict[str, Any]:

    try:
        # https://www.starlette.io/threadpool/
        results = await run_in_threadpool(
            create_jobs, index_name
        )

    except Exception as e:
        raise e

    logger.info(f'Got results: {results}')
    return {'number of batches': results}

@app.get("/health")
async def health() -> dict[str, Any]:
    logger.info('health route called')
    return {'status': 'ok', 'time': datetime.now()}
