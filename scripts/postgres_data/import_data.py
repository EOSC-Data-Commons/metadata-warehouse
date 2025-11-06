#!/usr/bin/env -S uv run --script
from pathlib import Path
from lxml import etree as ET
import requests
import traceback
import sys
from datetime import datetime, timezone
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}

FASTAPI_ADDRESS = os.environ.get('FASTAPI_ADDRESS', '127.0.0.1')

def import_data(repo_code: str, harvest_url: str, dir: Path, additional_dir: Optional[Path]) -> None:
    files: list[Path] = list(dir.rglob("*.xml"))
    harvest_run_id = None

    try:
        harvest_run = requests.post(f'http://{FASTAPI_ADDRESS}:8080/harvest_run', json={
            'harvest_url': harvest_url
        })

        harvest_run.raise_for_status()

        response = harvest_run.json()

        print(response)

        harvest_run_id = response.get('id')

        if harvest_run_id is None:
            raise ValueError('harvest_run_id not set')

    except Exception as e:
        print(f'An error occurred when loading data in DB: {e}', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    started = datetime.now(timezone.utc)

    for file in files:
        try:
            with open(file) as f:
                xml = f.read()

            # https://stackoverflow.com/questions/15830421/xml-unicode-strings-with-encoding-declaration-are-not-supported
            root = ET.fromstring(bytes(xml, encoding='utf-8'))
            identifier = root.find('./oai:header/oai:identifier', namespaces=NS)

            datestamp = root.find('./oai:header/oai:datestamp', namespaces=NS)

            if identifier is None or datestamp is None:
                raise ValueError(f'XML OAI-PMH record {file} without identifier or datestamp')

            additional_metadata = None
            if additional_dir:
                name_parts = os.path.basename(file).split('.oai')

                additional_file = list(additional_dir.rglob(f'{name_parts[0]}*'))

                if len(additional_file) == 1:
                    with open(additional_file[0]) as f2:
                        additional_metadata = f2.read()


            payload = {
                'record_identifier': identifier.text,
                'datestamp': datestamp.text,
                'raw_metadata': xml,
                'additional_metadata': additional_metadata,
                'harvest_url': harvest_url,
                'repo_code': repo_code,
                'harvest_run_id': harvest_run_id,
                'is_deleted': False
            }

            res = requests.post(f'http://{FASTAPI_ADDRESS}:8080/harvest_event', json=payload)

            res.raise_for_status()

            print(identifier.text)

        except Exception as e:
            print(f'An error occurred when loading data in DB: {e}', file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


    completed = datetime.now(timezone.utc)

    res = requests.put(f'http://{FASTAPI_ADDRESS}:8080/harvest_run', json={
        'id': harvest_run_id,
        'success': True,
        'started_at': started.strftime('%Y-%m-%d %H:%M:%S.%f%z'),
        'completed_at': completed.strftime('%Y-%m-%d %H:%M:%S.%f%z')
    })

    res.raise_for_status()

    print(res.json())

HARVEST_ENDPOINTS = [
    ('DANS', 'https://archaeology.datastations.nl/oai', Path('data/harvests_DANS_arch'), Path('data/harvests_DANS_arch_additional')),
    ('DANS', 'https://ssh.datastations.nl/oai', Path('data/harvests_DANS_soc'), Path('data/harvests_DANS_soc_additional')),
    ('DANS', 'https://lifesciences.datastations.nl/oai', Path('data/harvests_DANS_life'), Path('data/harvests_DANS_life_additional')),
    ('DANS', 'https://phys-techsciences.datastations.nl/oai', Path('data/harvests_DANS_phystech'), Path('data/harvests_DANS_phystech_additional')),
    ('DANS', 'https://dataverse.nl/oai', Path('data/harvests_DANS_gen'), Path('data/harvests_DANS_gen_additional')),
    ('SWISS', 'https://www.swissubase.ch/oai-pmh/v1/oai', Path('data/harvests_SWISS_dc_datacite'), None),
    ('DABAR', 'https://dabar.srce.hr/oai', Path('data/harvests_DABAR'), Path('data/harvests_DABAR_additional')),
    ('HAL', 'https://api.archives-ouvertes.fr/oai/hal', Path('data/harvests_HAL_sample'), None)
]

for repo, harvest_url, path, add in HARVEST_ENDPOINTS:
    import_data(repo, harvest_url, path, add)
