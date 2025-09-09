import os

class PostgresConfig:

    user: str
    password: str
    port: int

    def __init__(self):
        self.user = os.environ.get('POSTGRES_USER')
        self.password = os.environ.get('POSTGRES_PASSWORD')
        self.port = 5432
