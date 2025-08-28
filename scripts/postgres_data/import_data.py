#!/usr/bin/env -S uv run --script
import sys

import pgsql
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

user = os.environ.get('POSTGRES_ADMIN')
pw = os.environ.get('POSTGRES_PASSWORD')

files: list[Path] = (list(Path('data').rglob("*.xml")))

with pgsql.Connection(('127.0.0.1', 5432), user, pw, tls = False) as db:
    print(db)

    try:
        for file in files:

            with open(file) as f:
                xml = f.read()

            print(file)
            db.execute(f"""
            INSERT INTO raw (info)VALUES ( XMLPARSE(DOCUMENT '{xml.replace("'", "''")}'));
            """)
    except Exception as e:
        print(f'An error occurred when loading data in DB: {e}', file=sys.stderr)
