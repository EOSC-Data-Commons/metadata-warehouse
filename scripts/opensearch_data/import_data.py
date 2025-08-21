import json
from pathlib import Path
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
import sys

# setting path
sys.path.append("..")
sys.path.append("../..")

from src.utils.embedding_utils import preprocess_batch

def flush_bulk(client, batch):
    success, failed = bulk(client, batch)
    print(success, failed)


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

files: list[Path] = (list(Path('data/json_with_embedding').rglob("*.json")))

for file in files:

    source = json.load(open(file))

    batch.append(source)

    if len(batch) == batch_size:
        # calculate embeddings for batch
        preprocessed = preprocess_batch(batch, index_name)
        flush_bulk(client, preprocessed)
        batch = []

if len(batch) > 0:
    preprocessed = preprocess_batch(batch, index_name)
    flush_bulk(client, preprocessed)
