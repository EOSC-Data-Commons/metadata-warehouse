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

if not USER or not PW:
    raise ValueError('Missing POSTGRES_ADMIN or POSTGRES_PASSWORD in environment.')

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}

def import_data(repo_code: str, harvest_url: str, dir: Path) -> None:
    files: list[Path] = list(dir.rglob("*.xml"))

    with pgsql.Connection(('127.0.0.1', 5432), USER, PW, tls = False) as db:
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
                INSERT INTO harvest_events 
                    (record_identifier, 
                    raw_metadata, 
                    repository_id, 
                    endpoint_id, 
                    action, 
                    metadata_protocol,
                    metadata_format
                    ) 
                VALUES ( 
                    '{identifier.text}', 
                    XMLPARSE(DOCUMENT '{xml.replace("'", "''")}'), 
                    (SELECT id from repositories WHERE code='{repo_code}'),
                     (SELECT id from endpoints WHERE harvest_url='{harvest_url}'), 
                     'create', 
                     'OAI-PMH',
                      'XML');
                """)

                #break
        except Exception as e:
            print(f'An error occurred when loading data in DB: {e}', file=sys.stderr)


with pgsql.Connection(('127.0.0.1', 5432), USER, PW, tls=False) as db:
    try:
        res = db.execute(f"""
        TRUNCATE TABLE records;
        TRUNCATE TABLE harvest_events;
        """)
    except Exception as e:
        print(f'An error occurred when deleting data in DB: {e}', file=sys.stderr)


import_data('DANS', 'https://archaeology.datastations.nl/oai', Path('data/harvests_DANS_arch'))
import_data('DANS', 'https://ssh.datastations.nl/oai', Path('data/harvests_DANS_soc'))
import_data('DANS', 'https://lifesciences.datastations.nl/oai', Path('data/harvests_DANS_life'))
import_data('DANS', 'https://phys-techsciences.datastations.nl/oai', Path('data/harvests_DANS_phystech'))
import_data('DANS', 'https://dataverse.nl/oai', Path('data/harvests_DANS_gen'))
import_data('SWISS', 'https://www.swissubase.ch/oai-pmh/v1/oai', Path('data/harvests_SWISS_dc_datacite'))
import_data('DABAR', 'https://dabar.srce.hr/oai', Path('data/harvests_DABAR'))
import_data('HAL', 'https://api.archives-ouvertes.fr/oai/hal', Path('data/harvests_HAL_sample'))

