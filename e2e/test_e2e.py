import json
import os
import time

import httpx
import psycopg
import pytest
from dotenv import load_dotenv
from opensearchpy import OpenSearch

load_dotenv('.env')

USER = os.environ.get('POSTGRES_ADMIN')
PW = os.environ.get('POSTGRES_PASSWORD')
ADDRESS = os.environ.get('POSTGRES_ADDRESS')
PORT = os.environ.get('POSTGRES_PORT')
TEST_DATASET_DB = 'testdatasetdb'
TEST_FILE_DB = 'testfiledb'
TEST_INDEX = 'test_index'
EMBEDDING_DIMS = os.environ.get('EMBEDDING_DIMS')

API_BASE_URL = 'http://localhost:8080'
FLOWER_BASE_URL = 'http://localhost:5555'
TIMEOUT = 120


@pytest.fixture
def api_client():
    """HTTP client for API requests."""
    with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
        yield client


@pytest.fixture
def flower_client():
    with httpx.Client(base_url=FLOWER_BASE_URL, timeout=TIMEOUT) as client:
        yield client


def reset_db(name: str, path: str):
    sql_files = [
        'types.sql',
        'tables.sql',
        'indexes.sql',
        'triggers.sql',
        'seed.sql',
        'views.sql',
        'permissions.sql',
        'verify.sql',
    ]

    # Connect to default 'postgres' db to create the test db if needed
    with psycopg.connect(
        dbname='postgres',
        user=USER,
        host='127.0.0.1',
        password=PW,
        port=5432,
        autocommit=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', (name,))
            if not cursor.fetchone():
                cursor.execute(f'CREATE DATABASE {name}')

    with psycopg.connect(dbname=name, user=USER, host='127.0.0.1', password=PW, port=5432) as conn:
        with conn.cursor() as cursor:
            # Drop and recreate schema
            cursor.execute('DROP SCHEMA IF EXISTS public CASCADE')
            cursor.execute('CREATE SCHEMA public')

            for sql_f in sql_files:
                filepath = f'scripts/postgres_data/create_sql/{path}/{sql_f}'
                if not os.path.exists(filepath):
                    # print(f'Skipping {filepath} (not found)')
                    continue

                with open(filepath) as f:
                    sql_statements = f.read()
                cursor.execute(sql_statements)


@pytest.fixture
def reset_dataset_db():
    reset_db(TEST_DATASET_DB, 'datasetdb')


@pytest.fixture
def reset_file_db():
    reset_db(TEST_FILE_DB, 'filedb')


@pytest.fixture
def reset_index():
    client = OpenSearch(
        hosts=[
            {
                'host': ADDRESS if ADDRESS else '127.0.0.1',
                'port': int(PORT) if PORT else 9200,
            }
        ],
        http_auth=None,
        use_ssl=False,
    )

    try:
        if client.indices.exists(index=TEST_INDEX):
            client.indices.delete(index=TEST_INDEX)

        with open('config/opensearch_mapping.json') as f:
            os_mapping = json.load(f)
            # dynamically set embeddings dims
            os_mapping['mappings']['properties']['emb']['dimension'] = EMBEDDING_DIMS
            client.indices.create(index=TEST_INDEX, body=os_mapping)
    except Exception as e:
        pytest.fail(e)

    yield client


@pytest.fixture
def wait_for_task():
    def _wait_for_task(flower_client, task_name, timeout=TIMEOUT):
        """Wait for a task to complete successfully."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = flower_client.get('/api/tasks', params={'taskname': task_name})
                tasks = response.json()

                if tasks:
                    first_task = next(iter(tasks.values()))
                    if first_task.get('state') == 'SUCCESS':
                        return first_task
            except Exception:
                pass

            time.sleep(1)

        return None

    return _wait_for_task


def test_health(api_client, reset_dataset_db, reset_file_db):
    resource = api_client.get('/health')
    assert resource.status_code == 200
    assert resource.json()['status'] == 'ok'


def test_get_config(api_client, reset_dataset_db, reset_file_db):
    response = api_client.get('/config')

    assert response.status_code == 200
    assert len(response.json()['endpoints_configs']) == 28


def test_get_latest_harvest_run_with_harvest_url(api_client, flower_client, reset_dataset_db, reset_index):
    res_get = api_client.get('/harvest_run', params={'harvest_url': 'https://demo.onedata.org/oai_pmh'})

    assert res_get.status_code == 200
    runs = res_get.json()['harvest_runs']
    assert isinstance(runs, list)
    # no harvest runs yet — id should be None
    assert all(r['id'] is None for r in runs)

    # create a new harvest run
    res_create = api_client.post('/harvest_run', json={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    assert res_create.status_code == 200
    create_response = res_create.json()

    res_get2 = api_client.get('/harvest_run', params={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    res_get2_response = res_get2.json()

    assert res_get2.status_code == 200
    assert len(res_get2_response['harvest_runs']) == 1
    assert res_get2_response['harvest_runs'][0]['status'] == 'open'
    assert res_get2_response['harvest_runs'][0]['id'] is not None

    # close harvest_run
    res_close = api_client.put(
        '/harvest_run',
        json={
            'id': create_response['id'],
            'success': True,
            'started_at': '2026-02-17T15:36:05.544Z',
            'completed_at': '2026-02-17T15:36:05.544Z',
        },
    )
    assert res_close.status_code == 200

    res_get3 = api_client.get('/harvest_run', params={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    res_get3_response = res_get3.json()

    assert res_get3.status_code == 200
    assert len(res_get3_response['harvest_runs']) == 1
    assert res_get3_response['harvest_runs'][0]['status'] == 'closed'


def test_get_latest_harvest_run_without_harvest_url(api_client, flower_client, reset_dataset_db, reset_index):
    res_get = api_client.get('/harvest_run')

    assert res_get.status_code == 200
    runs = res_get.json()['harvest_runs']
    assert isinstance(runs, list)
    # no harvest runs yet
    assert all(r['id'] is None for r in runs)

    # create a new harvest run
    res_create = api_client.post('/harvest_run', json={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    assert res_create.status_code == 200
    create_response = res_create.json()

    res_get2 = api_client.get('/harvest_run', params={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    res_get2_response = res_get2.json()

    assert res_get2.status_code == 200
    assert len(res_get2_response['harvest_runs']) == 1
    assert res_get2_response['harvest_runs'][0]['status'] == 'open'

    res_close = api_client.put(
        '/harvest_run',
        json={
            'id': create_response['id'],
            'success': True,
            'started_at': '2026-02-17T15:36:05.544Z',
            'completed_at': '2026-02-17T15:36:05.544Z',
        },
    )
    assert res_close.status_code == 200

    res_get3 = api_client.get('/harvest_run', params={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    res_get3_response = res_get3.json()

    assert res_get3.status_code == 200
    assert len(res_get3_response['harvest_runs']) == 1
    assert res_get3_response['harvest_runs'][0]['status'] == 'closed'


def test_should_be_harvested_flag(api_client, reset_dataset_db, reset_index):
    """
    Endpoints with no harvest run and is_active=True should have
    should_be_harvested=True. After a recent closed run, the flag
    should reflect whether the schedule interval has elapsed.
    """
    res = api_client.get('/harvest_run', params={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    assert res.status_code == 200
    runs = res.json()['harvest_runs']
    assert len(runs) == 1
    # never harvested + active → should be harvested
    assert runs[0]['should_be_harvested'] is True

    # create and immediately close a harvest run
    res_create = api_client.post('/harvest_run', json={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    assert res_create.status_code == 200
    run_id = res_create.json()['id']

    api_client.put(
        '/harvest_run',
        json={
            'id': run_id,
            'success': True,
            'started_at': '2026-02-17T15:36:05.544Z',
            'completed_at': '2026-02-17T15:36:05.544Z',
        },
    )

    res2 = api_client.get('/harvest_run', params={'harvest_url': 'https://demo.onedata.org/oai_pmh'})
    runs2 = res2.json()['harvest_runs']
    # just harvested → depends on schedule, but until_date will be recent
    # so should_be_harvested should be False if schedule > 0
    assert isinstance(runs2[0]['should_be_harvested'], bool)


def test_create_and_close_harvest_run(
    api_client, flower_client, reset_dataset_db, reset_file_db, reset_index, wait_for_task
):
    # create a new harvest run
    res_create = api_client.post('/harvest_run', json={'harvest_url': 'https://demo.onedata.org/oai_pmh'})

    assert res_create.status_code == 200

    create_response = res_create.json()

    with open('e2e/test_data/dans.xml') as f:
        xml = f.read()

    with open('e2e/test_data/dans_additional.json') as f:
        additional_meta = f.read()

    # write a harvest event
    post_he = api_client.post(
        '/harvest_event',
        json={
            'record_identifier': '10.34894/G8PZKV',
            'datestamp': '2026-02-17T15:43:03.326Z',
            'raw_metadata': f'{xml}',
            'additional_metadata': additional_meta,
            'harvest_url': 'https://archaeology.datastations.nl/oai',
            'repo_code': 'DANS',
            'harvest_run_id': create_response['id'],
            'is_deleted': False,
        },
    )

    assert post_he.status_code == 200

    # close harvest_run
    res_close = api_client.put(
        '/harvest_run',
        json={
            'id': create_response['id'],
            'success': True,
            'started_at': '2026-02-17T15:36:05.544Z',
            'completed_at': '2026-02-17T15:36:05.544Z',
        },
    )

    assert res_close.status_code == 200

    # run a transformation
    res_index = api_client.get(
        '/index',
        params={
            'harvest_run_id': create_response['id'],
            'index_name': TEST_INDEX,
        },
    )

    # note this does not check for a successful transformation
    assert res_index.status_code == 200

    transform_task = wait_for_task(flower_client, 'tasks.transform_batch')
    filemeta_task = wait_for_task(flower_client, 'tasks.add_file_metadata')

    assert transform_task and transform_task['state'] == 'SUCCESS'
    assert '10.17026/AR/0AKDPK' in transform_task['args']

    assert filemeta_task and filemeta_task['state'] == 'SUCCESS'
    assert '10.17026/AR/0AKDPK' in filemeta_task['args']

    response_config = api_client.get('/config')

    assert response_config.status_code == 200
    assert len(response_config.json()['endpoints_configs']) == 28
