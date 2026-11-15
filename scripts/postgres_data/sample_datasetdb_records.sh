#!/usr/bin/env bash
set -euo pipefail

# Loaded from .env file
# HOST="your-db-host"
# PORT=5432
# DB_USER="your-db-user"
# DB_NAME="datasetdb"
set -a
source ".env"
set +a

TABLE="public.records"
SAMPLE_SIZE=1000
OUTPUT="records_sample.sql"
# PostgreSQL connection settings
export PGGSSENCMODE=disable
export PGCONNECT_TIMEOUT=30

# 1. Test connection and authentication
echo "Testing PostgreSQL connection to $HOST:$PORT..."

if ! psql \
    -w -X \
    -h "$HOST" \
    -p "$PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -v VERBOSITY=verbose \
    -c "SELECT 1"; then

    echo "ERROR: PostgreSQL connection failed."
    exit 1
fi

echo "Connection successful."

# 2. Create temporary dump file
TEMP_FILE=$(mktemp "${OUTPUT}.XXXXXX")
trap 'rm -f "$TEMP_FILE"' EXIT

# 3. Export schema and sample rows
echo "Dumping random $SAMPLE_SIZE of $TABLE..."

{
    pg_dump -w -h "$HOST" -p "$PORT" -U "$DB_USER" \
        -d "$DB_NAME" -t "$TABLE" \
        --schema-only --no-owner --no-privileges

    echo "COPY $TABLE FROM stdin;"

    psql -w -X -h "$HOST" -p "$PORT" -U "$DB_USER" \
    -d "$DB_NAME" -v ON_ERROR_STOP=1 \
    -c "COPY (
        SELECT *
        FROM $TABLE TABLESAMPLE SYSTEM (0.1)
        ORDER BY random()
        LIMIT $SAMPLE_SIZE
    ) TO STDOUT"

    printf '\\.\n'
} > "$TEMP_FILE"

# 4. Finalize only after successful dump
mv "$TEMP_FILE" "$OUTPUT"

echo "Dump completed: $OUTPUT"
du -h "$OUTPUT"
