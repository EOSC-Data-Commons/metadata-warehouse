from opensearchpy import OpenSearch
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

index_body = {
    'settings': {
        'index': {
            'number_of_shards': 1
        },
        'index.knn': True
    },
    'mappings': {
        'dynamic': False,
        'properties': {
            'titles': {
                'type': 'nested',
                'properties': {
                    'title':
                        {
                            'type': 'text',
                            'copy_to': '_all_fields'
                        }
                }
            },
            'emb': {
                "type": "knn_vector",
                "dimension": embedding_dims,
                "space_type": "cosinesimil",
                "method": {
                    "name": "hnsw",
                    "engine": "lucene",
                    "parameters": {
                        "encoder": {
                            "name": "sq"
                        },
                        "ef_construction": 256,
                        "m": 8
                    }
                }
            },
            '_all_fields': {
                'type': 'text'
            }
        }
    }
}

try:
    client.indices.create(index=index_name, body=index_body)
    print(f'{index_name} created')
except Exception as e:
    print(e)
