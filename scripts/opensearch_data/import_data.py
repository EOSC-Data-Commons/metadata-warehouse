import json
from pathlib import Path
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
from fastembed import TextEmbedding
import sys
from dotenv import load_dotenv
import os

load_dotenv()

embedding_model = os.environ['EMBEDDING_MODEL']
print(embedding_model)

# setting path
sys.path.append("..")
sys.path.append("../..")

from src.utils.embedding_utils import get_embedding_text_from_fields, preprocess_batch

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

batch_size = 500
index_name = 'test_datacite'

batch = []

files: list[Path] = (list(Path('data').rglob("*.json")))

embedding_transformer = TextEmbedding(model_name=embedding_model)

for file in files:

    # print('adding', len(batch), batch_size)

    source = json.load(open(file))

    batch.append((source, get_embedding_text_from_fields(source)))

    if len(batch) == batch_size:
        # calculate embeddings for batch
        flush_bulk(client, preprocess_batch(batch, embedding_transformer, index_name))
        batch = []

if len(batch) > 0:
    flush_bulk(client, preprocess_batch(batch, embedding_transformer, index_name))
