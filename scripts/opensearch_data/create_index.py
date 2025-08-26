#!/usr/bin/env python3

from opensearchpy import OpenSearch
import json
from dotenv import load_dotenv
import os

load_dotenv()

INDEX_NAME = os.environ.get('INDEX_NAME')
embedding_dims = os.environ.get('EMBEDDING_DIMS')

if not INDEX_NAME or not embedding_dims:
    raise ValueError("Missing INDEX_NAME or EMBEDDING_DIMS environment variable")

host = 'localhost'
client = OpenSearch(
    hosts=[{'host': host, 'port': 9200}],
    http_auth=None,
    use_ssl=False
)

try:
    client.indices.delete(
        index=INDEX_NAME
    )
    print(f'index {INDEX_NAME} deleted')
except Exception as e:
    print(e)

try:
    with open('../../src/config/opensearch_mapping.json') as f:
        os_mapping = json.load(f)
        # dynamically set embeddings dims
        os_mapping['mappings']['properties']['emb']['dimension'] = embedding_dims
        client.indices.create(index=INDEX_NAME, body=os_mapping)
        print(f'index {INDEX_NAME} created')
except Exception as e:
    print(e)
