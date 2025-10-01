#!/usr/bin/env -S uv run --script
import sys

import pgsql
import os
from dotenv import load_dotenv
from pathlib import Path
from lxml import etree as ET

load_dotenv()

USER = os.environ.get('POSTGRES_ADMIN')
PW = os.environ.get('POSTGRES_PASSWORD')

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}

files: list[Path] = (list(Path('data').rglob("harvests_DANS_arch/*.xml")))

with pgsql.Connection(('127.0.0.1', 5432), USER, PW, tls = False) as db:
    print(db)

    try:
        for file in files:

            with open(file) as f:
                xml = f.read()

            existing_tree = ET.parse(file)
            existing_root = existing_tree.getroot()
            identifier = existing_root.find("./oai:header/oai:identifier", namespaces=NS)

            if identifier is None:
                raise ValueError(f'XML OAI-PMH record {file} without identifier')

            print(identifier.text)

            # escape single quotes in XML content: https://www.postgresql.org/docs/current/sql-syntax-lexical.html#SQL-SYNTAX-STRINGS
            db.execute(f"""
            INSERT INTO harvest_events (record_identifier, raw_metadata, repository_id, endpoint_id, action, metadata_protocol) VALUES ( '{identifier.text}', XMLPARSE(DOCUMENT '{xml.replace("'", "''")}'), (SELECT id from repositories WHERE code='DANS'), (SELECT id from endpoints WHERE harvest_url='https://easy.dans.knaw.nl/oai'), 'create', 'OAI-PMH' );
            """)

            #break
    except Exception as e:
        print(f'An error occurred when loading data in DB: {e}', file=sys.stderr)
