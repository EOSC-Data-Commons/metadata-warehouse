#!/usr/bin/env -S uv run --script
import sys

import pgsql
import os
from dotenv import load_dotenv

load_dotenv()

#print(os.environ)

USER = os.environ.get('POSTGRES_ADMIN')
PW = os.environ.get('POSTGRES_PASSWORD')

sql_files = ['types.sql', 'tables.sql', 'indexes.sql']

with pgsql.Connection(('127.0.0.1', 5432), USER, PW, tls = False) as db:

    for sql_f in sql_files:
        try:
            with open(f'create_sql/{sql_f}') as f:
                sql_statements = f.read()
            res = db.execute(sql_statements)
            print(f'Executed {sql_f}')
        except Exception as e:
            print(f'An error occurred when creating DB: {e}', file=sys.stderr)



