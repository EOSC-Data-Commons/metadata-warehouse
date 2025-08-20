from opensearchpy import OpenSearch

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
                            'copy_to': ['_all_fields', '_title']
                        },
                    'lang': {
                        'type': 'keyword'
                    }
                }
            },
            'subjects': {
                'type': 'nested',
                'properties': {
                    'subject':
                        {
                            'type': 'text',
                            'copy_to': ['_all_fields', '_subject']
                        },
                    'lang': {
                        'type': 'keyword'
                    },
                    'subjectScheme': {
                        'type': 'keyword'
                    },
                    'schemaUri': {
                        'type': 'keyword'
                    },
                    'valueUri': {
                        'type': 'keyword'
                    },
                    'classificationCode': {
                        'type': 'keyword'
                    }
                }
            },
            '_all_fields': {
                'type': 'text'
            },
            '_title': {
                'type': 'text'
            },
            '_subject': {
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
