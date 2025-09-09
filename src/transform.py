from datetime import datetime
from logging.config import dictConfig
from pathlib import Path

import pgsql # type: ignore
from fastapi.concurrency import run_in_threadpool
#import psycopg2
from tasks import transform_batch
import os
from fastapi import FastAPI
from typing import Any
import logging
from config.logger import LOGGING_CONFIG

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

USER = os.environ.get('POSTGRES_USER')
PW = os.environ.get('POSTGRES_PASSWORD')
BATCH_SIZE = os.environ.get('CELERY_BATCH_SIZE')
if not BATCH_SIZE or not BATCH_SIZE.isnumeric():
    raise ValueError('Missing or invalid CELERY_BATCH_SIZE environment variable')

app = FastAPI()

def create_jobs(index_name: str) -> int:
    batch = []
    tasks = 0
    offset = 0
    limit = int(BATCH_SIZE) if BATCH_SIZE else 250
    fetch = True

    logger.info(f'Preparing jobs')
    with pgsql.Connection(('postgres', 5432), USER, PW, tls=False) as db:
        # print(db)

        while fetch:

            with db.prepare(f"""
            SELECT (xpath('/oai:record', info, '{{{{oai, http://www.openarchives.org/OAI/2.0/}},{{datacite, http://datacite.org/schema/kernel-4}}}}'))[1] AS root
        FROM raw
            ORDER BY ID
            LIMIT {limit}
            OFFSET {offset}
            """) as docs:

                for doc in docs():
                    batch.append(doc.root)

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
