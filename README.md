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

# Load Data

- `cd scripts`
- make a virtual env and install dependencies: `pip install -r requirements.txt`

## Create Postgres DB and Load and Transform Data

 - `cd scripts/postgres_data`
 - create DB `admin` with table `raw`: `python create_db`
 - load XML data from `scripts/postgres_data/data`: `python import_data.py`
 - query XML data: `python get_data`
 - transform data from `scripts/postgres_data/data` to a local dir: `python transform.py -i harvests_{repo_suffix} -o {repo_suffix}_json -s JSON_schema_file [-n]`
   If the -n flag is provided, the JSON data will also be normalized and validated against the JSON schema file `utils/schema.json`.

## Create OpenSearch Index and Import some Sample Data

- `cd scripts/opensearch_data`
- create index `test_datacite`: `python create_index.py`
- load JSON data in Datacite format from `scripts/opensearch_data/data`: `python import_data.py`
- perform a query like (requires host port mapping 9200 for opensearch):
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

## Dependencies

Dependencies are mentioned in [DEPENDENCIES.md](DEPENDENCIES.md).
