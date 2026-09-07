#!/usr/bin/env bash

set -e

./create_db.py --db datasetdb
./create_db.py --db filedb
./create_db.py --db tooldb

# Only creates the database; airflow migrates its own schema on start, see create_sql/airflowdb/
./create_db.py --db airflowdb

