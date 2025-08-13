# Metadata Warehouse

## Usage

This repo contains a `docker-compose.yml` to run an instance `postgres` and `opensearch` with their respective UIs.
To run the containers:
- `cp env.template .env` (adjust env variables as needed and set new passwords)
- `cp docker-compose.override.yml.template docker-compose.override.yml` (adjust as needed)
- `docker compose up -d`

