class OpenSearchConfig:

    host: str
    port: int

    def __init__(self) -> None:
        self.host = 'opensearch'
        self.port = 9200
