import os

class PostgresConfig:

    user: str
    password: str
    port: int

    def __init__(self) -> None:
        user = os.environ.get('POSTGRES_USER')
        password = os.environ.get('POSTGRES_PASSWORD')

        if user and password:
            self.user = user
            self.password = password
            self.address = 'postgres'
            self.port = 5432
        else:
            raise ValueError('Missing POSTGRES_USER or POSTGRES_PASSWORD in environment (docker-compose.yml).')

