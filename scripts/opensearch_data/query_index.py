from dotenv import load_dotenv
import os
from fastembed import TextEmbedding
from opensearchpy import OpenSearch
import json

load_dotenv()

host = 'localhost'
client = OpenSearch(
    hosts=[{'host': host, 'port': 9200}],
    http_auth=None,
    use_ssl=False
)

embedding_model = os.environ['EMBEDDING_MODEL']

embedding_transformer = TextEmbedding(model_name=embedding_model)

query_strings = ['What is a mathematical formula?']

embeddings = list(embedding_transformer.embed(query_strings))

os_query = {
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

res = client.search(index='test_datacite', body=os_query)

print(json.dumps(res))
