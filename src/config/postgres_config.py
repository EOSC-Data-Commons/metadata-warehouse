import os
from typing import Any

class PostgresConfig:

    user: str
    db: str
    password: str
    address: str
    port: int

    def __init__(self) -> None:
        user = os.environ.get('POSTGRES_USER')
        db = os.environ.get('POSTGRES_DB')
        password = os.environ.get('POSTGRES_PASSWORD')
        address = os.environ.get('POSTGRES_ADDRESS')
        port = os.environ.get('POSTGRES_PORT')

        if user and password and db:
            self.user = user
            self.password = password
            self.db = db
            self.address = address if address else 'postgres'
            self.port = int(port) if port else 5432
        else:
            raise ValueError('Missing POSTGRES_USER or POSTGRES_PASSWORD or POSTGRES_DB in environment (docker-compose.yml).')

    @property
    def connection_params(self) -> dict[str, Any]:
        """Connection parameters for psycopg."""
        return {
            'dbname': self.db,
            'user': self.user,
            'host': self.address,
            'password': self.password,
            'port': self.port
        }
