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
- API keys for mcp server:
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

### pgAdmin

- when using pgAdmin, register a new server with `Host name` "postgres" (container name in docker network) with port "5432".
- provide credentials as defined in `.env`.

## Basic Setup

- ```shell
  cd scripts
  ```
- Install [uv](https://docs.astral.sh/uv/) and run
  ```sh
  uv sync
  ```

### Create Postgres DB and Load and Transform Data

- ```sh
  cd scripts/postgres_data
  ```

- create table structure and repo config as defined in `scripts/postgres_data/create_sql`
  (to start from scratch, you have to remove the tables first with [DROP](https://www.postgresql.org/docs/current/sql-droptable.html)):
  ```sh
  uv run create_db.py
  ```

- load XML data from `scripts/postgres_data/data` (populates table `harvest_events`):
  ```sh
   uv run import_data.py
  ```

- transform data from `scripts/postgres_data/data` to a local dir
  (to test transformation, alternative to using the Celery process):
  ```sh
  uv run transform.py -i harvests_{repo_suffix} -o {repo_suffix}_json -s JSON_schema_file [-n]
  ```
  If the -n flag is provided, the JSON data will also be normalized and validated against the JSON schema file `utils/schema.json`.

### Create OpenSearch Index

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

### Run Transformation Process

The transformer container provides an [API](http://127.0.0.1:8080/docs) to start the transformation and indexing process.

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

- start transformation process:
  ```sh
  http://127.0.0.1:8080/index?harvest_run_id=xyz
  ```
- see transformation task results in flower:
  ```sh
  http://127.0.0.1:5555/tasks
  ```

## Development

Install pre-commit hooks to run all checks automatically on commit:

```sh
uv run pre-commit install
```

Run linters manually:

```sh
uvx ruff format
uvx ruff check --fix
uv run mypy
```

