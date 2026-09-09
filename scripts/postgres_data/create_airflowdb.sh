#!/bin/sh
# Runs once, at postgres cluster initialization, from /docker-entrypoint-initdb.d.
#
# Airflow migrates its own schema on every start and cannot wait for init_dbs.sh, which is run by
# hand after the stack is up, so its database has to exist before the first airflow connection.
# Only the database. The tables are airflow's own, written by `airflow db migrate`, which the
# api-server runs on every start (_AIRFLOW_DB_MIGRATE in docker-compose.yml), so there is no schema
# for create_db.py to manage and no airflowdb folder under create_sql/.
#
# Never point create_db.py at airflowdb: --reset drops schema public, which is airflow's entire
# metadata (DAG history, task instances, connections).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE DATABASE airflowdb;
SQL
