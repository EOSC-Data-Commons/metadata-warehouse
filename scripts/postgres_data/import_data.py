#!/usr/bin/env -S uv run --script
import os
from dotenv import load_dotenv
from pathlib import Path
from lxml import etree as ET
import requests
import traceback
import sys
import json

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}

def import_data(repo_code: str, harvest_url: str, dir: Path) -> None:
    files: list[Path] = list(dir.rglob("*.xml"))

    for file in files:

        try:
            with open(file) as f:
                xml = f.read()

            root = ET.fromstring(xml)
            identifier = root.find("./oai:header/oai:identifier", namespaces=NS)

            if identifier is None:
                raise ValueError(f'XML OAI-PMH record {file} without identifier')

            payload = {
                'record_identifier': identifier.text,
                'raw_metadata': xml,
                'harvest_url': harvest_url,
                'repo_code': repo_code
            }

            res = requests.post('http://127.0.0.1:8080/harvest_event', json=payload)

            res.raise_for_status()

            print(identifier.text)

        except Exception as e:
            print(f'An error occurred when loading data in DB: {e.with_traceback}', file=sys.stderr)
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
