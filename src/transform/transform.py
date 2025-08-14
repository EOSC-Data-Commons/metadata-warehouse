import pgsql
#import psycopg2
from opensearchpy import OpenSearch
from tasks import celery_app, add


#with pgsql.Connection(("postgres", 5432), "admin", "test", tls = False) as db:
    #print(db)


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

print('putting some tasks into queue')

for n in range(10):
    result = add.delay(4, 70)
    print(result)
    print(f'added {n} task')
