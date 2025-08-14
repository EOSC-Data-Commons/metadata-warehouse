import pgsql
#import psycopg2
from opensearchpy import OpenSearch
from tasks import celery_app, add, transform_batch
import os

#print(os.environ)

user = os.environ['POSTGRES_USER']
pw = os.environ['POSTGRES_PASSWORD']

batch = []

with pgsql.Connection(('postgres', 5432), user, pw, tls = False) as db:
    print(db)

    with db.prepare("""
    SELECT xpath('/oai:record', info, '{{oai, http://www.openarchives.org/OAI/2.0/},{datacite, http://datacite.org/schema/kernel-4}}') AS root
FROM raw;
    """) as docs:

        all_rows = docs()
        #print(len(all_rows))

        for doc in all_rows():
            batch.append(doc.root)


res = transform_batch.delay(batch)
print(res)




#conn = psycopg2.connect(database = 'postgres', user= 'admin', password= 'test', host= 'postgres', port = 5432)
#cursor = conn.cursor()
#print(cursor)

'''
host = 'opensearch'
client = OpenSearch(
    hosts=[{'host': host, 'port': 9200}],
    http_auth=None,
    use_ssl=False
)

print(f'opensearch client info: {client.info()}')
'''

'''
print('putting some tasks into queue')

for n in range(10):
    result = add.delay(4, 70)
    print(result)
    print(f'added {n} task')
'''