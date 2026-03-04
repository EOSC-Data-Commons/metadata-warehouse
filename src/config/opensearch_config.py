import os

class OpenSearchConfig:

    host: str
    port: int

    def __init__(self) -> None:
        address = os.environ.get('OPENSEARCH_ADDRESS')
        port = os.environ.get('OPENSEARCH_PORT')

        self.host = address if address else 'opensearch'
        self.port = int(port) if port else 9200
