#!/usr/bin/env bash
set -e

# Load .env
export $(grep -v '^#' .env | xargs)

PGHOST=$POSTGRES_ADDRESS
PGPORT=$POSTGRES_PORT
PGUSER=$POSTGRES_ADMIN
PGPASSWORD=$POSTGRES_PASSWORD
export PGPASSWORD

SQL_DIR="./create_sql"

echo "=== [1] Creating global users ==="
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$POSTGRES_DB" -f "$SQL_DIR/user.sql"

echo "=== [2] Creating databases ==="
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$POSTGRES_DB" -f "$SQL_DIR/createDB.sql"

echo "=== [3] Configuring datasetdb ==="
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d datasetdb -f "$SQL_DIR/datasetDBconfig.sql"

echo "=== [4] Configuring filedb ==="
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d filedb -f "$SQL_DIR/fileDBconfig.sql"

echo "=== [5] Configuring tooldb ==="
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d tooldb -f "$SQL_DIR/toolDBconfig.sql"

echo "=== [6] Configuring appdb ==="
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d appdb -f "$SQL_DIR/appDBconfig.sql"

echo "=== [7] Assigning access ==="
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$POSTGRES_DB" -f "$SQL_DIR/access.sql"

echo
echo "=== ALL DONE ==="
