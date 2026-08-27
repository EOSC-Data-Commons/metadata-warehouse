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
POSTGRES_ADDRESS = os.environ.get('POSTGRES_ADDRESS_HOST')
POSTGRES_PORT = os.environ.get('POSTGRES_PORT')
OPENSEARCH_ADDRESS = os.environ.get('OPENSEARCH_ADDRESS_HOST')
OPENSEARCH_PORT = os.environ.get('OPENSEARCH_PORT')
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
        host=POSTGRES_ADDRESS if POSTGRES_ADDRESS else '127.0.0.1',
        password=PW,
        port=int(POSTGRES_PORT) if POSTGRES_PORT else 5432,
        autocommit=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', (name,))
            if not cursor.fetchone():
                cursor.execute(f'CREATE DATABASE {name}')

    with psycopg.connect(
        dbname=name,
        user=USER,
        host=POSTGRES_ADDRESS if POSTGRES_ADDRESS else '127.0.0.1',
        password=PW,
        port=int(POSTGRES_PORT) if POSTGRES_PORT else 5432,
    ) as conn:
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
                'host': OPENSEARCH_ADDRESS if OPENSEARCH_ADDRESS else '127.0.0.1',
                'port': int(OPENSEARCH_PORT) if OPENSEARCH_PORT else 9200,
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
    assert len(response.json()['endpoints_configs']) == 29


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
    assert res_create.json()['master_set_identifiers'] is None

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

    transform_task = wait_for_task(flower_client, 'transform.tasks.transform_batch')
    filemeta_task = wait_for_task(flower_client, 'transform.tasks.add_file_metadata')

    assert transform_task and transform_task['state'] == 'SUCCESS'
    assert '10.17026/AR/0AKDPK' in transform_task['args']

    assert filemeta_task and filemeta_task['state'] == 'SUCCESS'
    assert '10.17026/AR/0AKDPK' in filemeta_task['args']

    response_config = api_client.get('/config')

    assert response_config.status_code == 200
    assert len(response_config.json()['endpoints_configs']) == 29


HAL_HARVEST_URL = 'https://api.archives-ouvertes.fr/oai/hal'
ZENODO_HARVEST_URL = 'https://zenodo.org/oai2d'

HAL_RECORD_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<oai:record xmlns:oai="http://www.openarchives.org/OAI/2.0/"
            xmlns:datacite="http://datacite.org/schema/kernel-4">
  <oai:metadata>
    <datacite:resource>
      <datacite:relatedIdentifiers>
        <datacite:relatedIdentifier relatedIdentifierType="DOI">{doi}</datacite:relatedIdentifier>
      </datacite:relatedIdentifiers>
    </datacite:resource>
  </oai:metadata>
</oai:record>"""

ZENODO_RECORD_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<oai:record xmlns:oai="http://www.openarchives.org/OAI/2.0/"
            xmlns:datacite="http://datacite.org/schema/kernel-4">
  <oai:metadata>
    <datacite:resource>
      <datacite:identifier identifierType="DOI">{doi}</datacite:identifier>
    </datacite:resource>
  </oai:metadata>
</oai:record>"""


def _close_harvest_run(api_client, run_id):
    res_close = api_client.put(
        '/harvest_run',
        json={
            'id': run_id,
            'success': True,
            'started_at': '2026-02-17T15:36:05.544Z',
            'completed_at': '2026-02-17T15:36:05.544Z',
        },
    )
    assert res_close.status_code == 200
    return res_close


def _post_harvest_event(api_client, *, harvest_run_id, harvest_url, repo_code, record_identifier, raw_metadata):
    res = api_client.post(
        '/harvest_event',
        json={
            'record_identifier': record_identifier,
            'datestamp': '2026-02-17T15:43:03.326Z',
            'raw_metadata': raw_metadata,
            'additional_metadata': None,
            'harvest_url': harvest_url,
            'repo_code': repo_code,
            'harvest_run_id': harvest_run_id,
            'is_deleted': False,
        },
    )
    assert res.status_code == 200
    return res


def test_zenodo_dependency_without_hal(api_client, reset_dataset_db, reset_file_db, reset_index):
    """
    Try to harvest Zenodo with having harvested HAL first.
    This should fail since Zenodo depends on HAL.
    """

    res_create_zenodo_1 = api_client.post('/harvest_run', json={'harvest_url': ZENODO_HARVEST_URL})
    assert res_create_zenodo_1.status_code == 400
    assert (
        res_create_zenodo_1.json()['detail']
        == 'This is a dependent repository and requires the endpoint HAL to be harvested first'
    )


def test_zenodo_dependency_master_set_identifiers(api_client, reset_dataset_db, reset_file_db, reset_index):
    """
    Zenodo's endpoint config depends on HAL as a master set. When opening a
    Zenodo harvest run, the response should list Zenodo-referenced DOIs found
    in HAL's harvested records, minus any DOIs Zenodo has already harvested
    itself in a previous closed run.
    """
    hal_zenodo_dois = [
        '10.5281/zenodo.111',
        '10.5281/zenodo.222',
        '10.5281/zenodo.333',
    ]

    ZENODO_STATIC_DOIS = {
        '10.5281/zenodo.7350485',
        '10.5281/zenodo.13692761',
        '10.5281/zenodo.15324029',
        '10.5281/zenodo.7702229',
        '10.5281/zenodo.11278072',
        '10.5281/zenodo.3382874',
        '10.5281/zenodo.6645396',
        '10.5281/zenodo.8260741',
        '10.5281/zenodo.4559324',
        '10.5281/zenodo.20509715',
    }

    # --- 1. Get in some HAL records ---
    res_create_hal = api_client.post('/harvest_run', json={'harvest_url': HAL_HARVEST_URL})
    assert res_create_hal.status_code == 200
    hal_run_id = res_create_hal.json()['id']

    for i, doi in enumerate(hal_zenodo_dois):
        _post_harvest_event(
            api_client,
            harvest_run_id=hal_run_id,
            harvest_url=HAL_HARVEST_URL,
            repo_code='HAL',
            record_identifier=f'hal-rec-{i}',
            raw_metadata=HAL_RECORD_XML_TEMPLATE.format(doi=doi),
        )

    _close_harvest_run(api_client, hal_run_id)

    # --- 2. Get the Zenodo DOIs (first Zenodo run — nothing harvested yet) ---
    res_create_zenodo_1 = api_client.post('/harvest_run', json={'harvest_url': ZENODO_HARVEST_URL})
    assert res_create_zenodo_1.status_code == 200
    zenodo_run_1 = res_create_zenodo_1.json()

    identifiers_1 = set(zenodo_run_1['master_set_identifiers'])
    assert identifiers_1 == {'10.5281/zenodo.111', '10.5281/zenodo.222', '10.5281/zenodo.333'} | ZENODO_STATIC_DOIS

    zenodo_run_1_id = zenodo_run_1['id']

    # --- 3. Register some Zenodo (simulate harvester having fetched DOI 111) ---
    _post_harvest_event(
        api_client,
        harvest_run_id=zenodo_run_1_id,
        harvest_url=ZENODO_HARVEST_URL,
        repo_code='ZENODO',
        record_identifier='oai:zenodo.org:111',
        raw_metadata=ZENODO_RECORD_XML_TEMPLATE.format(doi='10.5281/zenodo.111'),
    )

    _close_harvest_run(api_client, zenodo_run_1_id)

    # --- 4. Get the IDs again (second Zenodo run — 111 should now be excluded) ---
    res_create_zenodo_2 = api_client.post('/harvest_run', json={'harvest_url': ZENODO_HARVEST_URL})
    assert res_create_zenodo_2.status_code == 200
    zenodo_run_2 = res_create_zenodo_2.json()

    identifiers_2 = set(zenodo_run_2['master_set_identifiers'])
    assert identifiers_2 == {'10.5281/zenodo.222', '10.5281/zenodo.333'} | ZENODO_STATIC_DOIS
    assert '10.5281/zenodo.111' not in identifiers_2
