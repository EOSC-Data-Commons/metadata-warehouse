# Metadata Warehouse

## Docker Compose Setup

This repo contains a `docker-compose.yml` file which configures the containers and their interaction.
To run the containers:
- users and passwords (adjust env variables as needed and set new passwords):
  ```sh
  cp env.template .env
  ```
  Optionally add the following env variables for postgres and/or OpenSearch (not needed for local dev):
    - `POSTGRES_ADDRESS` (default "postgres") and `POSTGRES_PORT` (default 5432)
    - `OPENSEARCH_ADDRESS` (default "opensearch") and `OPENSEARCH_PORT` (default 9200)
    - `FASTAPI_ADDRESS` (default "127.0.0.1") and `FASTAPI_PORT` (default 8080)
- API keys for search API server:
  ```sh
  cp keys.env.template keys.env
  ```
- Dev config for docker containers:
  ```sh
  cp docker-compose.override.yml.template docker-compose.override.yml
  ```
- ```sh
  docker compose up -d
  ```
- generate the two Airflow secrets, see [Airflow](#airflow).
- create postgreSQL table structure, see below.
- create OpenSearch index, see below.
- run transformation process, see below.

## pgAdmin

- when using pgAdmin, register a new server with `Host name` "postgres" (container name in docker network) with port "5432".
- provide credentials as defined in `.env`.

# Basic Setup

- ```shell
  cd scripts
  ```
- Install [uv](https://docs.astral.sh/uv/) and run
  ```sh
  uv sync --frozen
  ```

## Prepare Data For Local Import

In production, the DB is populated by running the crawler.
In development, it may be more convenient to load pre-harvested static data:
- create a folder per repository, e.g., `scripts/postgres_data/data/dans_arch`
- create an XML file containing records such as
  ```xml
  <Records xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
     <record xmlns="http://www.openarchives.org/OAI/2.0/">
     ...
     </record>
     ...
  </Records>
  ```
- fetch additional metadata using `scripts/postgres_data/dataverse.py` (Dataverse) or `scripts/postgres_data/get_meta.py` (HAL, Zenodo)
  Combine additional metadata files in one virtual structure using

  Dataverse:
   ```python
    import json, glob

    lookup = {}
    for f in glob.glob('*.json'):
        with open(f) as fh:
            obj = json.load(fh)
        key = obj["data"]["datasetPersistentId"]
        lookup[key] = obj  # or just the fields you need

    # Optionally save it
    with open('lookup.json', 'w') as out:
        json.dump(lookup, out)
  ```

  HAL:
  ```python
  import json, glob

    lookup = {}
    for f in glob.glob('*.json'):
        with open(f) as fh:
            obj = json.load(fh)
        if len(obj["response"]["docs"]) == 1:
            key = obj["response"]["docs"][0]["halId_s"]
            lookup[key] = obj  # or just the fields you need
        else:
            print(f)
            print(obj)

    # Optionally save it
    with open('lookup.json', 'w') as out:
        json.dump(lookup, out)
  ```
- check the settings in `scripts/postgres_data/import_data.py`:
  ```python
  HARVEST_ENDPOINTS = [
    ('DANS', 'https://archaeology.datastations.nl/oai', Path('data/dans_arch/dans_arch.xml'), Path('doi_dataverse/lookup.json'), None)
  ```
  where `data/dans_arch/dans_arch.xml` contains the OAI-PMH records and `doi_dataverse/lookup.json` the additional metadata.

## Create Postgres DB and Load and Transform Data

- ```sh
  cd scripts/postgres_data
  ```

- create table structure and repo config as defined in `scripts/postgres_data/create_sql/$dbname`
  ```sh
  uv run create_db.py --db $dbname [--reset]
  ```
  This will create and init the specified DB if it does not exist yet.
  If it already exists and should be **dropped and reinitialized**,
  additionally provide the flag --reset.

- load XML data from `scripts/postgres_data/data` (populates table `harvest_events`):
  ```sh
   uv run import_data.py
  ```
  See [Prepare Data For Local Import](#Prepare-Data-For-Local-Import) for further details about local data preparation.

- transform data from `scripts/postgres_data/data` to a local dir
  (to test transformation, alternative to running the `harvest_pipeline` DAG):
  ```sh
  uv run transform.py -i harvests_{repo_suffix} -o {repo_suffix}_json -s JSON_schema_file [-n] [-v]
  ```
  If the -n flag is provided, the JSON data will be normalized
  (the raw JSON may look differently based on the input XML, see these [specs](https://www.xml.com/pub/a/2006/05/31/converting-between-xml-and-json.html)).
  If the -v flag is set, the JSON will be validated against the JSON schema file `utils/schema.json`

## Create OpenSearch Index

- ```sh
  cd scripts/opensearch_data
  ```

- create `test_datacite` index (deletes existing `test_datacite` index):

  ```sh
  uv run create_index.py
  ```

- for sample OpenSearch queries, see [open_search_queries](docs/open_search_queries.md)
- to test queries requiring vector embeddings, run
  ```sh
  uv run query_index.py
  ```

## Run Transformation Process

Transformation and indexing are run by Airflow, see [Airflow](#airflow) below. The transformer
container provides an [API](http://127.0.0.1:8080/docs) for the harvest runs and events the
pipeline reads.

A transformation requires a `harvest_run_id`.
When running the script `import_data.py` (scripts/postgres_data/data),
for each endpoint a harves run is created, the single OAI-PMH records are registered as harvest events,
and the harvest run is then closed. Note that a transformation can only be performed for a closed harvest run.

- check if transformer container is up and running:
  ```sh
  http://127.0.0.1:8080/health
  ```

- To obtain a harvest run id and status for a given endpoint (https://dabar.srce.hr/oai):
  ```sh
  http://127.0.0.1:8080/harvest_run?harvest_url=https%3A%2F%2Fdabar.srce.hr%2Foai
  ```

- start the transformation for the closed runs, and watch it in the Airflow UI
  (http://127.0.0.1:8081):
  ```sh
  docker compose exec airflow-scheduler airflow dags trigger harvest_pipeline
  ```

## Airflow

Airflow runs every python job in this repo. The
DAGs are in [`dags/`](dags/), the jobs they call are in [`src/transform/`](src/transform/).

1 DAG `harvest_pipeline`: harvest the due endpoints, wait for their runs to close, transform every closed run batch by batch, then index into appDB

The UI is on http://127.0.0.1:8081 (log in with `AIRFLOW_ADMIN` / `AIRFLOW_ADMIN_PASSWORD`).

### Setup

Two secrets have no sensible default, generate them into `.env` once:

```sh
uv run python -c "from cryptography.fernet import Fernet; print('AIRFLOW_FERNET_KEY=' + Fernet.generate_key().decode())" >> .env
echo "AIRFLOW_JWT_SECRET=$(openssl rand -hex 32)" >> .env
```

On Linux, also set `AIRFLOW_UID` to your own `id -u` so the mounted `dags/` and the fastembed cache
stay writable. The `airflowdb` database is created by `scripts/postgres_data/init_dbs.sh` with
every other warehouse database; the api-server migrates its schema and creates the admin user on
every start, so there is no init container.

### Architecture

Five containers: `airflow-apiserver`, `airflow-scheduler`, `airflow-dag-processor`,
`airflow-worker` and `broker`. The first three are the floor for Airflow 3, which split DAG parsing
out of the scheduler and routes task state through the api-server. `CeleryExecutor` has the
scheduler publish tasks to the RabbitMQ `broker` and the workers pull them, so capacity is added by
adding workers rather than by growing one host:

```sh
docker compose up -d --scale airflow-worker=3
```

`AIRFLOW_WORKER_CONCURRENCY` is the slot count per worker container and `AIRFLOW_PARALLELISM` the
cluster wide ceiling; both matter because each transformation task loads its own embedding model, so
they are bounded by RAM rather than by CPU. Queue depth is visible in Flower, off by default:

```sh
docker compose --profile flower up -d flower
```

The transformation fans out with **dynamic task mapping**: one mapped task per batch of
`TRANSFORM_BATCH_SIZE` harvest events, each retried and logged on its own. Mapped arguments travel
through the metadata DB, so the tasks map over `(harvest_run_id, start_id, limit)` descriptors and
each reads its own records with keyset pagination, see
[`src/transform/batches.py`](src/transform/batches.py).

### Harvesting

`harvest_endpoint` runs the crawler in process from the `metadata-harvester` package, one mapped
task per endpoint. A plain trigger harvests every endpoint whose `harvest_schedule` has elapsed, so
pin the endpoints to keep a run small:

```sh
docker compose exec airflow-scheduler airflow dags trigger harvest_pipeline \
  --conf '{"harvest_urls": ["https://repository.dasch.swiss/dpe/oai"]}'
```

A partial harvest does not fail the task: a feed that repeats a record identifier has those records
rejected with a 409 and its run closed as `failed`, and the records that did land are still
transformed. One unreachable endpoint therefore cannot keep the others out of the warehouse.

### Dependent endpoints

Some repositories are configured as dependent endpoints in the `endpoints` table by setting
`depends_on_endpoint_id`. A dependent endpoint uses identifiers collected from its master
endpoint, so `list_endpoints_to_harvest` always returns independent endpoints first and moves
dependent endpoints to the end of the same batch. This ensures HAL is harvested before Zenodo when
both endpoints are due for harvesting.

### Working on the DAGs

`dags/`, `src/` and `config/` are bind mounted into the Airflow containers, so an edit is picked up
by the dag-processor without a rebuild. A dependency change needs
`docker compose build airflow-scheduler`.

```sh
# any airflow CLI command runs in the scheduler container, there is no separate cli service
docker compose exec airflow-scheduler airflow dags list
docker compose exec airflow-scheduler airflow dags list-import-errors

# run one task on its own, printing its log to the terminal
docker compose exec airflow-scheduler airflow tasks test harvest_pipeline list_closed_runs
```

#### Environment variables

Optionally add the following env variables (not needed for local dev):

- `WAREHOUSE_API_URL` (default "http://transform:80")
- `INDEX_NAME` (default "test_datacite")

## Linting

To format all files properly, run:

- `uv run ruff format`
- `uv run ruff check --select I --fix`

## Run E2E Tests

Before running the e2e tests locally, set the env vars `POSTGRES_DB` and `FILE_DB`
to `testdatasetdb` and `testfiledb`, respectively, since the e2e tests and the API
must use the same DBs.

Note that the e2e tests reset `testdatasetdb` and `testfiledb` on each run. Because
the test DB names are hardcoded in the e2e tests, your production DBs will not be
overwritten.

To run the e2e tests:
```sh
uv run pytest -s e2e
```

## Commit Message Conventions

Keep to this commit message [style](https://www.conventionalcommits.org/en/v1.0.0/#summary).
For semantic versioning, see these [release-please](https://github.com/googleapis/release-please#how-should-i-write-my-commits).
Set up pre-commit hooks to check your messages before commiting them to the repo:
- `uv sync --frozen --all-extras --dev`
- `uv run pre-commit install --hook-type commit-msg`

See `.pre-commit-config.yaml` for further details.
