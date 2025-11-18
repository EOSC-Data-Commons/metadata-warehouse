#!/usr/bin/env -S uv run --script

from dotenv import load_dotenv
import os
from fastembed import TextEmbedding
from opensearchpy import OpenSearch
import json

load_dotenv()

INDEX_NAME = os.environ.get('INDEX_NAME')
EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL')
ADDRESS = os.environ.get('OPENSEARCH_ADDRESS')
PORT = os.environ.get('OPENSEARCH_PORT')
if not INDEX_NAME or not EMBEDDING_MODEL:
    raise ValueError("Missing INDEX_NAME environment variable")

client = OpenSearch(
    hosts=[{'host': ADDRESS if ADDRESS else '127.0.0.1', 'port': int(PORT) if PORT else 9200}],
    http_auth=None,
    use_ssl=False
)

embedding_model = os.environ['EMBEDDING_MODEL']

embedding_transformer = TextEmbedding(model_name=embedding_model)

query_strings = ['What is a mathematical formula?']

embeddings = list(embedding_transformer.embed(query_strings))

opensearch_query = {
    "_source": ["titles.title", "subjects.subject", "descriptions.description"],
    "query": {
        "knn": {
            "emb": {
                "vector": embeddings[0].tolist(),
                "k": 5
            }
        }
    }
}

res = client.search(index=INDEX_NAME, body=opensearch_query)

print(json.dumps(res, indent=2, ensure_ascii=False))
