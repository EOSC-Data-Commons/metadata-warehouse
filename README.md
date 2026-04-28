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

## Run E2E Tests

Before running the e2e tests locally, the env var `POSTGRES_DB` needs to be set to "testdb" 
since the e2e tests and the API have to use the same DB in order for the tests to work. 
Note that the e2e tests reinit "testdb" on each run. Since "testdb" is hardcoded in the e2e tests, 
the productive db "dataset" won't be overwritten by running the e2e tests. 

To run the e2e tests:
```sh
uv run pytest -s e2e
```

## Use devenv.nix for local deploy/test development environment

### Install Nix

- Linux and Windows (WSL2):

```console
sh <(curl -L https://nixos.org/nix/install) --daemon
```

- macOS

```console
curl -L https://github.com/NixOS/experimental-nix-installer/releases/download/0.27.0/nix-installer.sh | sh -s -- install
```

- Docker 

Be careful with this approach where the caching is lost after container stopped.

```console
docker run -it nixos/nix
```

For more details if you get stucked, check [here](https://devenv.sh/getting-started/#1-install-nix)

### Install devenv

```console
nix-env --install --attr devenv -f https://github.com/NixOS/nixpkgs/tarball/nixpkgs-unstable
```

If you already know nix you probably want to install it though: nix profile, nix-darwin or through home-manager, check [here](https://devenv.sh/getting-started/#2-install-devenv)

### (optional) Configure a GitHub access token

To avoid being rate-limited, **we recommend providing Nix with a GitHub access token**, which will greatly increase your API limits.

Create a new token with no extra permissions at https://github.com/settings/personal-access-tokens/new. Add the token to your ``~/.config/nix/nix.conf``:

```console
access-tokens = github.com=<GITHUB_TOKEN>
```

check [here](https://devenv.sh/getting-started/#3-configure-a-github-access-token-optional) for details.

### Spin up services

The environment is setup, to start all services run 

```console
devenv run -v
```

### Import data

We need database include the havested data and indexing for opensearch.
The database was already havested and can be requst from Tobias Schweizer (@tobiasschweizer).

Download the data file (`dump.sql.zip`) from the [releases page](https://github.com/EOSC-Data-Commons/dev-environment/releases/).
Unzip it and place the resulting `dump.sql` file in the repository root.

Import the data with:

```console
devenv tasks run db-import
```

This import task takes about 30s to finish it import the dump, and create indexing for a small data repository. 

```console
python repo-index.py list
```

to get all available data repositories and then to indexing run:

```console
python repo-index.py indexing <repo-url>
```

Fill `<repo-url>` with a repo url.

Here is a summary of the number of entries in each data repository: [1]

[1] https://confluence.egi.eu/display/EOSCDATACOMMONS/2025-11-21+Work+Group+1+Update

### Clean up and reset

#### Cleanup and re-import the database

The postgresql service need keep on running to clean up the database.

To clean imported data, run:

```console
devenv tasks run clean:db
```

You can then import from dump and indexing for opensearch.

#### Cleanup and reset python/npm environments

To clean python venv run 

```console
devenv tasks run clean:python
```

This will delete the `venv` folder in the project (at `./.devenv/state/venv`).

You can then reset the environment by `devenv tasks run setup:python`.

#### Cleanup and reset the whole environment

Cleanup tasks are provide to reset the environment if anything goes wrong and you want to have a clean start.

To clean all caches and start environment from scratch run:

```console
devenv tasks run purge
```
