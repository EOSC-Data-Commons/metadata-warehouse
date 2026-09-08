import os


class OpenSearchConfig:
    host: str
    port: int

    def __init__(self) -> None:
        address = os.environ.get('OPENSEARCH_ADDRESS_DOCKER')
        port = os.environ.get('OPENSEARCH_PORT_DOCKER')

        self.host = address if address else 'opensearch'
        self.port = int(port) if port else 9200
