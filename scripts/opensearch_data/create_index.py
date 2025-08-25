#!/usr/bin/env python3

from opensearchpy import OpenSearch
import json
from dotenv import load_dotenv
import os

load_dotenv()

embedding_dims = os.environ['EMBEDDING_DIMS']
print(embedding_dims)

host = 'localhost'
client = OpenSearch(
    hosts=[{'host': host, 'port': 9200}],
    http_auth=None,
    use_ssl=False
)

print(f'opensearch client info: {client.info()}')

index_name = 'test_datacite'

try:
    client.indices.delete(
        index=index_name
    )
    print(f'{index_name} deleted')
except Exception as e:
    print(e)

try:
    with open('../../src/config/os_mapping.json') as f:
        client.indices.create(index=index_name, body=json.load(f))
        print(f'{index_name} created')
except Exception as e:
    print(e)
