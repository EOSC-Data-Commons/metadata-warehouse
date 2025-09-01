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
logger.setLevel(logging.INFO)

# https://konfuzio.com/de/konfiguration-des-fastapi-loggings-lokal-und-in-der-produktion/
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter("%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s")
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

user = os.environ.get('POSTGRES_USER')
pw = os.environ.get('POSTGRES_PASSWORD')

app = FastAPI()

def create_jobs(index_name: str):
    batch = []

    logger.info(f'Preparing jobs')
    with pgsql.Connection(('postgres', 5432), user, pw, tls=False) as db:
        # print(db)

        with db.prepare("""
        SELECT (xpath('/oai:record/oai:metadata', info, '{{oai, http://www.openarchives.org/OAI/2.0/},{datacite, http://datacite.org/schema/kernel-4}}'))[1] AS root
    FROM raw
        LIMIT 500
        """) as docs:
            all_rows = docs()
            # print(len(all_rows))

            for doc in all_rows():
                batch.append(doc.root)

    # TODO: Backends use resources to store and transmit results. To ensure that resources are released, you must eventually call get() or forget() on EVERY AsyncResult instance returned after calling a task.
    # https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#keeping-results
    logger.info(f'Putting batch of {len(batch)} in queue')
    task: AsyncResult[int] = transform_batch.delay(batch, index_name)

    return {'batch of': len(batch), 'task_id': task.task_id}


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
    return results

