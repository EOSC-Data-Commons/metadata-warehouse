#!/usr/bin/env -S uv run --script
import sys
import os
import argparse
from dotenv import load_dotenv
import psycopg
import traceback

load_dotenv()

USER = os.environ.get('POSTGRES_ADMIN')
PW = os.environ.get('POSTGRES_PASSWORD')
ADDRESS = os.environ.get('POSTGRES_ADDRESS')
PORT = os.environ.get('POSTGRES_PORT')

if not USER or not PW:
    raise ValueError('Missing POSTGRES_ADMIN or POSTGRES_PASSWORD in environment.')

parser = argparse.ArgumentParser(description='Run SQL setup files for a given database.')
parser.add_argument('--db', required=True, help='Database name (also used as the SQL folder name)')
parser.add_argument('--reset', action='store_true', help='Reset the schema if the database already exists')
args = parser.parse_args()

DB = args.db
SQL_FOLDER = os.path.join('create_sql', args.db)

if not os.path.isdir(SQL_FOLDER):
    print(f'Error: SQL folder "{SQL_FOLDER}" does not exist.', file=sys.stderr)
    sys.exit(1)

sql_files = ['types.sql', 'tables.sql', 'indexes.sql', 'triggers.sql', 'seed.sql', 'views.sql', 'permissions.sql',
             'verify.sql']

host = ADDRESS if ADDRESS else '127.0.0.1'
port = int(PORT) if PORT else 5432

try:
    # Step 1: Create DB if it doesn't exist, or reset if --reset flag is set
    proceed = False

    with psycopg.connect(dbname='postgres', user=USER, host=host, password=PW, port=port,
                         autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB,))
            exists = cur.fetchone()
            if not exists:
                cur.execute(f'CREATE DATABASE "{DB}"')
                print(f'Database "{DB}" created.')
                proceed = True
            elif args.reset:
                print(f'Database "{DB}" already exists — resetting schema.')
                proceed = True
            else:
                print(f'Database "{DB}" already exists and --reset not specified. Exiting.')
                sys.exit(0)

    # Step 2: Reset schema and run all SQL files in a single transaction
    if proceed:
        with psycopg.connect(dbname=DB, user=USER, host=host, password=PW, port=port) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
                cur.execute("CREATE SCHEMA public")
                print('Schema "public" reset.')

                for sql_f in sql_files:
                    filepath = os.path.join(SQL_FOLDER, sql_f)
                    if not os.path.exists(filepath):
                        print(f'Skipping {filepath} (not found)')
                        continue
                    with open(filepath) as f:
                        sql_statements = f.read()
                    cur.execute(sql_statements)
                    print(f'Executed {filepath}')

            print('All SQL files executed successfully.')

except Exception as e:
    print(f'An error occurred: {e}', file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
