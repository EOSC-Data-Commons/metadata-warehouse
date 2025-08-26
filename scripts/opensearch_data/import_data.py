#!/usr/bin/env python3

import json
from pathlib import Path
from opensearchpy import OpenSearch
import sys
from opensearchpy.helpers import bulk, BulkIndexError
import os
from dotenv import load_dotenv

load_dotenv()

# setting path
sys.path.append("..")
sys.path.append("../..")

from src.utils.embedding_utils import preprocess_batch

INDEX_NAME = os.environ.get('INDEX_NAME')
if not INDEX_NAME:
    raise ValueError("Missing INDEX_NAME environment variable")

BATCH_SIZE = 5000
DATA_DIR = Path('data/json_with_embedding')

def flush_bulk(client, batch):
    try:
        success, failed = bulk(client, batch, max_retries=3)
        print(success, failed)
    except BulkIndexError as e:
        print(f'An error occurred: {e.errors}')

files: list[Path] = list(DATA_DIR.rglob('*.json'))

host = 'localhost'
client = OpenSearch(
    hosts=[{'host': host, 'port': 9200}],
    http_auth=None,
    use_ssl=False
)

batch = []

for file in files:

    with open(file) as f:
        source = json.load(f)

        batch.append(source)

        if len(batch) >= BATCH_SIZE:
            # calculate embeddings for batch
            preprocessed = preprocess_batch(batch, INDEX_NAME)
            flush_bulk(client, preprocessed)
            batch = []

if len(batch) > 0:
    preprocessed = preprocess_batch(batch, INDEX_NAME)
    flush_bulk(client, preprocessed)
