import pgsql # type: ignore
#import psycopg2
from tasks import transform_batch
import os
from fastapi import FastAPI

user = os.environ.get('POSTGRES_USER')
pw = os.environ.get('POSTGRES_PASSWORD')

app = FastAPI()

@app.get("/index")
async def index(index_name: str) -> dict[str, str]:
    batch = []

    with pgsql.Connection(('postgres', 5432), user, pw, tls=False) as db:
        # print(db)

        with db.prepare("""
        SELECT (xpath('/oai:record/oai:metadata', info, '{{oai, http://www.openarchives.org/OAI/2.0/},{datacite, http://datacite.org/schema/kernel-4}}'))[1] AS root
    FROM raw
        LIMIT 1000
        """) as docs:
            all_rows = docs()
            # print(len(all_rows))

            for doc in all_rows():
                batch.append(doc.root)

    transform_batch.delay(batch, index_name)

    return {'put into batch:': f'{len(batch)}'}
