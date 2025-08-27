# Metadata Warehouse

## Usage

This repo contains a `docker-compose.yml` to run an instance `postgres` and `opensearch` with their respective UIs.
To run the containers:
- `cp env.template .env` (adjust env variables as needed and set new passwords)
- `cp docker-compose.override.yml.template docker-compose.override.yml` (adjust as needed)
- `docker compose up -d`

## pgAdmin 

- when using pgAdmin, register a new server with `Host name` "postgres" (container name in docker network) with port "5432".  
- provider credentials as defined in `.env`

# Basic Setup and Loading Data

- `cd scripts`
- Install [uv](https://docs.astral.sh/uv/) and run `uv sync`

## Create Postgres DB and Load and Transform Data

 - `cd scripts/postgres_data`
 - create DB `admin` with table `raw`: `uv run create_db`
 - load XML data from `scripts/postgres_data/data`: `uv run import_data.py`
 - query XML data: `uv run get_data.py`
 - transform data from `scripts/postgres_data/data` to a local dir: `uv run transform.py -i harvests_{repo_suffix} -o {repo_suffix}_json -s JSON_schema_file [-n]`
   If the -n flag is provided, the JSON data will also be normalized and validated against the JSON schema file `utils/schema.json`.

## Create OpenSearch Index and Import some Sample Data

- ```sh
  cd scripts/opensearch_data
  ```

- create `test_datacite` index: 

  ```sh
  uv run create_index.py
  ```

- pre-calculate embeddings from JSON data in Datacite format `scripts/opensearch_data/data/json`:
  
  ```sh
  uv run prepare_data.py
  ```
  
  JSON files with embeddings will be written to `scripts/opensearch_data/data/json_with_embedding` 

- load JSON data in Datacite format with pre-calculated embeddings from `scripts/opensearch_data/data/json_with_embedding`:

  ```sh
  uv run import_data.py
  ```

- perform a lexical query like (requires host port mapping 9200 for opensearch):

  ```sh
  curl '127.0.0.1:9200/test_datacite/_search' -H 'Content-Type: application/json' -d '{
    "query": {
      "query_string": {
            "default_operator": "AND",
            "default_field": "_all_fields",
            "query": "math*"
          }
    }
  }' | jq
  ```
- `uv run query_index.py` to run a knn query

