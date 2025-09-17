#!/usr/bin/env -S uv run --script
import sys

import pgsql
import os
from dotenv import load_dotenv

load_dotenv()

#print(os.environ)

USER = os.environ.get('POSTGRES_ADMIN')
PW = os.environ.get('POSTGRES_PASSWORD')

with pgsql.Connection(('127.0.0.1', 5432), USER, PW, tls = False) as db:

    try:
        db.execute("""
        DROP TABLE raw;
        CREATE TABLE raw( id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, info XML, valid boolean, reason TEXT);
        """)
    except Exception as e:
        print(f'An error occurred when creating DB: {e}', file=sys.stderr)



