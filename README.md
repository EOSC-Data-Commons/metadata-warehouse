# Metadata Warehouse

## Docker Compose Setup

This repo contains a `docker-compose.yml` file which configures the containers and their interaction.
To run the containers:
- users and passwords (adjust env variables as needed and set new passwords):
  ```sh
  cp env.template .env`
  ```
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

## pgAdmin 

- when using pgAdmin, register a new server with `Host name` "postgres" (container name in docker network) with port "5432".  
- provide credentials as defined in `.env`.

# Basic Setup

- ```shell
  cd scripts
  ```
- Install [uv](https://docs.astral.sh/uv/) and run 
  ```sh
  uv sync
  ```
  
## Create Postgres DB and Load and Transform Data

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

- check if transformer container is up and running:
  ```sh
  http://127.0.0.1:8080/health
  ```
- start transformation process:
  ```sh
  http://127.0.0.1:8080/index?index_name=test_datacite
  ```
- see transformation task results in flower:
  ```sh
  http://127.0.0.1:5555/tasks
  ```
