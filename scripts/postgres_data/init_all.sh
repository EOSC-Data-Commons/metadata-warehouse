#!/usr/bin/env bash
set -e

SQL_DIR="./create_sql"

echo "=== [1] Creating global users ==="
psql -h "$POSTGRES_ADDRESS" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$SQL_DIR/user.sql"

echo "=== [2] Creating databases ==="
psql -h "$POSTGRES_ADDRESS" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$SQL_DIR/createDB.sql"

echo "=== [3] Configuring datasetdb ==="
psql -h "$POSTGRES_ADDRESS" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d datasetdb -f "$SQL_DIR/datasetDBconfig.sql"

echo "=== [4] Configuring filedb ==="
psql -h "$POSTGRES_ADDRESS" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d filedb -f "$SQL_DIR/fileDBconfig.sql"

echo "=== [5] Configuring tooldb ==="
psql -h "$POSTGRES_ADDRESS" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d tooldb -f "$SQL_DIR/toolDBconfig.sql"

echo "=== [6] Configuring appdb ==="
psql -h "$POSTGRES_ADDRESS" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d appdb -f "$SQL_DIR/appDBconfig.sql"

echo "=== [7] Assigning access ==="
psql -h "$POSTGRES_ADDRESS" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$SQL_DIR/access.sql"

echo
echo "=== ALL DONE ==="
