# Metadata Warehouse

The Metadata Warehouse stores data harvested by the [crawler](https://github.com/EOSC-Data-Commons/metadata-crawlers/) and transforms and validates this data for discovery.
For an architecture overview of how the different components interact, see https://doi.org/10.5281/zenodo.21068516.

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
  (to test transformation, alternative to using the Celery process):
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

The transformer container provides an [API](http://127.0.0.1:8080/docs) to start the transformation and indexing process.

A transformation requires a `harvest_run_id`.
When running the script `import_data.py` (scripts/postgres_data/data),
for each endpoint a harves run is created, the single OAI-PMH records are registered as harvest events,
and the harvest run is then closed. Note that a transformation can only be performed for a closed harvest run.

- check if transformer container is up and running:
  ```sh
  http://127.0.0.1:8080/health
  ```

- To obtain a harvest run id and status for a given endpoint (https://dabar.srce.hr/oai/):
  ```sh
  http://127.0.0.1:8080/harvest_run?harvest_url=https%3A%2F%2Fdabar.srce.hr%2Foai%2F
  ```

- start transformation process:
  ```sh
  http://127.0.0.1:8080/index?harvest_run_id=xyz&index_name=test_datacite
  ```
- see transformation task results in flower:
  ```sh
  http://127.0.0.1:5555/tasks
  ```

After starting the stack with `docker compose up`, you can run the harvester for a given repository URL, e.g.:

```sh
docker compose run harvester https://lifesciences.datastations.nl/oai
```
## Scheduler

The scheduler automates the full ingestion workflow: harvesting → transformation → indexing.
It is designed to be executed periodically via CRON.

### Run scheduler

```sh
uv run python -m scheduler.run
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

