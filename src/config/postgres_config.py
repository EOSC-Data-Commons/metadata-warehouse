import os

class PostgresConfig:

    user: str
    password: str
    address: str
    port: int

    def __init__(self) -> None:
        user = os.environ.get('POSTGRES_USER')
        db = os.environ.get('POSTGRES_DB')
        password = os.environ.get('POSTGRES_PASSWORD')
        address = os.environ.get('POSTGRES_ADDRESS')
        port = os.environ.get('POSTGRES_PORT')

        if user and password:
            self.user = user
            self.password = password
            self.db = db
            self.address = address if address else 'postgres'
            self.port = int(port) if port else 5432
        else:
            raise ValueError('Missing POSTGRES_USER or POSTGRES_PASSWORD in environment (docker-compose.yml).')
