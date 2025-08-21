#!/usr/bin/env python3

import json
from pathlib import Path
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, BulkIndexError


def flush_bulk(client, batch):
    try:
        success, failed = bulk(client, batch, max_retries=3)
        print(success, failed)
    except BulkIndexError as e:
        print(f'An error occurred: {e.errors}')

host = 'localhost'
client = OpenSearch(
    hosts=[{'host': host, 'port': 9200}],
    http_auth=None,
    use_ssl=False
)

print(client.info())

batch_size = 5000
index_name = 'test_datacite'

batch = []

files: list[Path] = (list(Path('data').rglob("*.json")))

for file in files:

    print('adding', len(batch), batch_size)
    batch.append({"_op_type": "index", "_index": index_name, "_source": json.load(open(file))})

    if len(batch) == batch_size:
        print('bulk')
        flush_bulk(client, batch)
        batch = []


if len(batch) > 0:
    flush_bulk(client, batch)

