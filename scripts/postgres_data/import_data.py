#!/usr/bin/env -S uv run --script
import sys
import traceback
import pgsql
import os
from dotenv import load_dotenv
from pathlib import Path
from lxml import etree as ET

load_dotenv()

USER = os.environ.get('POSTGRES_ADMIN')
PW = os.environ.get('POSTGRES_PASSWORD')
ADDRESS = os.environ.get('POSTGRES_ADDRESS')
PORT = os.environ.get('POSTGRES_PORT')

if not USER or not PW:
    raise ValueError('Missing POSTGRES_ADMIN or POSTGRES_PASSWORD in environment.')

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}


def import_data(repo_code: str, harvest_url: str, dir: Path) -> None:
    files: list[Path] = list(dir.rglob("*.xml"))

    with pgsql.Connection((ADDRESS if ADDRESS else '127.0.0.1', int(PORT) if PORT else 5432), USER, PW, tls=False) as db:
        try:
            for file in files:

                with open(file) as f:
                    xml = f.read()

                root = ET.fromstring(xml)
                identifier = root.find("./oai:header/oai:identifier", namespaces=NS)

                if identifier is None:
                    raise ValueError(f'XML OAI-PMH record {file} without identifier')

                print(f'record identifier: {identifier.text}')

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

        except Exception as e:
            print(f'An error occurred when loading data in DB: {e}', file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


HARVEST_ENDPOINTS = [
    ('DANS', 'https://archaeology.datastations.nl/oai', Path('data/harvests_DANS_arch')),
    ('DANS', 'https://ssh.datastations.nl/oai', Path('data/harvests_DANS_soc')),
    ('DANS', 'https://lifesciences.datastations.nl/oai', Path('data/harvests_DANS_life')),
    ('DANS', 'https://phys-techsciences.datastations.nl/oai', Path('data/harvests_DANS_phystech')),
    ('DANS', 'https://dataverse.nl/oai', Path('data/harvests_DANS_gen')),
    ('SWISS', 'https://www.swissubase.ch/oai-pmh/v1/oai', Path('data/harvests_SWISS_dc_datacite')),
    ('DABAR', 'https://dabar.srce.hr/oai', Path('data/harvests_DABAR')),
    ('HAL', 'https://api.archives-ouvertes.fr/oai/hal', Path('data/harvests_HAL_sample'))
]

for repo, harvest_url, path in HARVEST_ENDPOINTS:
    import_data(repo, harvest_url, path)
