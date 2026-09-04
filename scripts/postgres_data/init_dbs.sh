#!/usr/bin/env bash

set -e

./create_db.py --db datasetdb
./create_db.py --db filedb
./create_db.py --db tooldb
./create_db.py --db appdb

