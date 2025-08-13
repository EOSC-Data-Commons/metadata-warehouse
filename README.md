# Metadata Warehouse

## Usage

This repo contains a `docker-compose.yml` to run an instance `postgres` and `opensearch` with their respective UIs.
To run the containers:
- `cp env.template .env` (adjust env variables as needed and set new passwords)
- `cp docker-compose.override.yml.template docker-compose.override.yml` (adjust as needed)
- `docker compose up -d`

## Create OpenSearch Index and Import some Sample Data

- `cd opensearch_data`
- make a virtual env and install dependencies: `pip install -r requirements.txt`
- create index `test_datacite`: `python create_index.py`
- load JSON data in Datacite format from `opensearch_data/data`: `python import_data.py`
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