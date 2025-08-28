#!/usr/bin/env -S uv run --script
import sys

import pgsql
import os
from dotenv import load_dotenv

load_dotenv()

#print(os.environ)

user = os.environ.get('POSTGRES_ADMIN')
pw = os.environ.get('POSTGRES_PASSWORD')

with pgsql.Connection(('127.0.0.1', 5432), user, pw, tls = False) as db:

    try:
        db.execute("""
        DROP TABLE raw;
        CREATE TABLE raw( id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, info XML);
        """)
    except Exception as e:
        print(f'An error occurred when creating DB: {e}', file=sys.stderr)



