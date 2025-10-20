#!/usr/bin/env -S uv run --script
import sys
import os
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

sql_files = ['types.sql', 'tables.sql', 'indexes.sql', 'triggers.sql', 'seed.sql', 'views.sql', 'permissions.sql',
             'verify.sql']

try:
    with psycopg.connect(dbname=USER, user=USER, host=ADDRESS if ADDRESS else '127.0.0.1', password=PW,
                         port=int(PORT) if PORT else 5432) as conn:
        cur = conn.cursor()
        for sql_f in sql_files:
            try:
                with open(f'create_sql/{sql_f}') as f:
                    sql_statements = f.read()
                res = cur.execute(sql_statements)
                print(f'Executed {sql_f}')
            except Exception as e:
                print(f'An error occurred when creating DB with {sql_f}: {e}', file=sys.stderr)
except Exception as e:
    print(f'An error occurred when loading data in DB: {e}', file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
