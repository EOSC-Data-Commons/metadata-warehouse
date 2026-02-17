import httpx
import pytest
import psycopg
import os
from dotenv import load_dotenv

load_dotenv('.env')

USER = os.environ.get('POSTGRES_ADMIN')
PW = os.environ.get('POSTGRES_PASSWORD')
ADDRESS = os.environ.get('POSTGRES_ADDRESS')
PORT = os.environ.get('POSTGRES_PORT')
TEST_DB = 'test'

API_BASE_URL = "http://localhost:8080"

@pytest.fixture
def api_client():
    """HTTP client for API requests."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        yield client


@pytest.fixture
def reset_db():
    sql_files = ['types.sql', 'tables.sql', 'indexes.sql', 'triggers.sql', 'seed.sql', 'views.sql', 'permissions.sql',
                 'verify.sql']

    # Connect to default 'postgres' db to create the test db if needed
    with psycopg.connect(dbname='postgres', user=USER, host=ADDRESS if ADDRESS else '127.0.0.1', password=PW,
                         port=int(PORT) if PORT else 5432) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,))
            if not cursor.fetchone():
                cursor.execute(f"CREATE DATABASE {TEST_DB}")

    with psycopg.connect(dbname=TEST_DB, user=USER, host=ADDRESS if ADDRESS else '127.0.0.1', password=PW,
                         port=int(PORT) if PORT else 5432) as conn:
        with conn.cursor() as cursor:
            # Drop and recreate schema
            cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cursor.execute("CREATE SCHEMA public")

            for sql_f in sql_files:
                with open(f'scripts/postgres_data/create_sql/{sql_f}') as f:
                    sql_statements = f.read()
                cursor.execute(sql_statements)

def test_health(api_client, reset_db):

    resource = api_client.get("/health")
    assert resource.status_code == 200
    assert resource.json()['status'] == "ok"

def test_get_config(api_client, reset_db):

    response = api_client.get("/config")

    assert response.status_code == 200
    assert len(response.json()['endpoints_configs']) == 9
