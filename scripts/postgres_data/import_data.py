#!/usr/bin/env -S uv run --script
import sys
import traceback
import os
from dotenv import load_dotenv
from pathlib import Path
from lxml import etree as ET
import psycopg

load_dotenv()

USER = os.environ.get('POSTGRES_ADMIN')
PW = os.environ.get('POSTGRES_PASSWORD')

if not USER or not PW:
    raise ValueError('Missing POSTGRES_ADMIN or POSTGRES_PASSWORD in environment.')

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}


def import_data(repo_code: str, harvest_url: str, dir: Path) -> None:
    files: list[Path] = list(dir.rglob("*.xml"))

    try:
        conn = psycopg.connect(dbname='admin', user=USER, host='127.0.0.1', password=PW, port=5432)

        with conn.cursor() as curs:
            for file in files:
                with open(file) as f:
                    xml = f.read()

                # https://stackoverflow.com/questions/15830421/xml-unicode-strings-with-encoding-declaration-are-not-supported
                root = ET.fromstring(bytes(xml, encoding='utf-8'))
                identifier = root.find("./oai:header/oai:identifier", namespaces=NS)

                if identifier is None:
                    raise ValueError(f'XML OAI-PMH record {file} without identifier')

                print(f'record identifier: {identifier.text}')

                curs.execute("""
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
                                    %s, 
                                    XMLPARSE(DOCUMENT %s), 
                                    (SELECT id from repositories WHERE code=%s),
                                    (SELECT id from endpoints WHERE harvest_url=%s), 
                                    %s, 
                                    %s,
                                    %s);
                                """, (identifier.text, xml, repo_code, harvest_url, 'create', 'OAI-PMH', 'XML'))

        # not sure if this works for a whole repo like HAL
        conn.commit()
        conn.close()
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
