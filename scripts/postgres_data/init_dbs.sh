#!/usr/bin/env bash

set -e

./create_db.py --db dataset
./create_db.py --db recordfiles


