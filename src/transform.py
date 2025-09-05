from datetime import datetime
import pgsql # type: ignore
from celery.result import AsyncResult
from fastapi.concurrency import run_in_threadpool
#import psycopg2
from tasks import transform_batch
import os
from fastapi import FastAPI
from typing import Any
import logging
import sys

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# https://konfuzio.com/de/konfiguration-des-fastapi-loggings-lokal-und-in-der-produktion/
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter("%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s")
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

USER = os.environ.get('POSTGRES_USER')
PW = os.environ.get('POSTGRES_PASSWORD')
BATCH_SIZE = os.environ.get('CELERY_BATCH_SIZE')
if not BATCH_SIZE or not BATCH_SIZE.isnumeric():
    raise ValueError('Missing or invalid CELERY_BATCH_SIZE environment variable')

app = FastAPI()

def create_jobs(index_name: str) -> int:
    batch = []
    tasks = []
    offset = 0
    limit = int(BATCH_SIZE) if BATCH_SIZE else 250
    fetch = True

    logger.info(f'Preparing jobs')
    with pgsql.Connection(('postgres', 5432), USER, PW, tls=False) as db:
        # print(db)

        while fetch:

            with db.prepare(f"""
            SELECT (xpath('/oai:record/oai:metadata', info, '{{{{oai, http://www.openarchives.org/OAI/2.0/}},{{datacite, http://datacite.org/schema/kernel-4}}}}'))[1] AS root
        FROM raw
            ORDER BY ID
            LIMIT {limit}
            OFFSET {offset}
            """) as docs:

                for doc in docs():
                    batch.append(doc.root)

            # TODO: Backends use resources to store and transmit results. To ensure that resources are released, you must eventually call get() or forget() on EVERY AsyncResult instance returned after calling a task.
            # https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#keeping-results
            logger.info(f'Putting batch of {len(batch)} in queue with offset {offset}')
            task: AsyncResult[int] = transform_batch.delay(batch, index_name)
            tasks.append(task)

            # increment offset by limit
            offset = offset + limit
            # will be false if query returned fewer results than limit
            fetch = len(batch) == limit
            batch = []


    return len(tasks)


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
    return {'status': 'ok', 'time': datetime.now()}
