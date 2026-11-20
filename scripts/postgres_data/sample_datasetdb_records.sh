#!/usr/bin/env bash
set -euo pipefail

# ---------- Restore Script -------------- #
# CREATE USER $LOCAL_DB_USER with password '**********';
# CREATE DATABASE datasetdb owner $LOCAL_DB_USER;
#### If table exists, it needs to be dropped first
# psql -h localhost -U $LOCAL_DB_USER  -d datasetdb  -v ON_ERROR_STOP=1  -f records_sample.sql

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
    # Export all custom trigger functions used by the table
    psql -w -X -qAt \
        -h "$HOST" -p "$PORT" -U "$DB_USER" -d "$DB_NAME" \
        -v ON_ERROR_STOP=1 \
        -c "
        SELECT DISTINCT
            rtrim(pg_get_functiondef(p.oid), E' \n\t;') || ';'
        FROM pg_trigger t
        JOIN pg_proc p ON p.oid = t.tgfoid
        WHERE t.tgrelid = '$TABLE'::regclass
        AND NOT t.tgisinternal;
        "

    # Export custom enum types
    psql -w -X -qAt \
        -h "$HOST" -p "$PORT" -U "$DB_USER" -d "$DB_NAME" \
        -v ON_ERROR_STOP=1 \
        -c "
        SELECT format(
            'CREATE TYPE %I.%I AS ENUM (%s);',
            n.nspname,
            t.typname,
            string_agg(quote_literal(e.enumlabel), ', ' ORDER BY e.enumsortorder)
        )
        FROM pg_attribute a
        JOIN pg_type t ON t.oid = a.atttypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        JOIN pg_enum e ON e.enumtypid = t.oid
        WHERE a.attrelid = 'public.records'::regclass
          AND a.attnum > 0
          AND NOT a.attisdropped
        GROUP BY n.nspname, t.typname;
        "

    # Export table schema
    pg_dump -w -h "$HOST" -p "$PORT" -U "$DB_USER" \
        -d "$DB_NAME" -t "$TABLE" \
        --schema-only --no-owner --no-privileges

    # Export sampled records
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
