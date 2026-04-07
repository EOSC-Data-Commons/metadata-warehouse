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
from typing import cast

load_dotenv()

NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "datacite": "http://datacite.org/schema/kernel-4"}

FASTAPI_ADDRESS = os.environ.get('FASTAPI_ADDRESS', '127.0.0.1')
FASTAPI_PORT = os.environ.get('FASTAPI_PORT', '8080')
TIMEOUT_FASTAPI = 30

TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S.%f%z'


def import_data(repo_code: str, harvest_url: str, data_file: Path, additional_dir: Optional[Path], limit: Optional[int]) -> None:
    harvest_run_id = None

    try:
        harvest_run = requests.post(f'http://{FASTAPI_ADDRESS}:{FASTAPI_PORT}/harvest_run', json={
            'harvest_url': harvest_url
        }, timeout=TIMEOUT_FASTAPI)

        harvest_run.raise_for_status()

        response = harvest_run.json()

        harvest_run_id = response.get('id')

        if harvest_run_id is None:
            raise ValueError('harvest_run_id not set')

    except Exception as e:
        print(f'An error occurred when creating a harvest run: {e}', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise e

    started = datetime.now(timezone.utc)

    try:
        with open(data_file) as f:
            xml = f.read()

        # https://stackoverflow.com/questions/15830421/xml-unicode-strings-with-encoding-declaration-are-not-supported
        root = ET.fromstring(bytes(xml, encoding='utf-8'))

        records = cast(list[ET._Element], root.xpath('./oai:record[oai:header[@status!="deleted"]]', namespaces=NS))

        count = 0
        for record in records:

            prefix = 'datacite' if repo_code != 'HAL' else 'oai'

            oai_id = record.find(f'./oai:header/oai:identifier', namespaces=NS)

            if oai_id is None or oai_id.text is None:
                raise ValueError(f'XML OAI-PMH record {record} without identifier')

            oai_id_without_prefix = oai_id.text.split(':')[-1]

            identifier = record.find(f'./oai:metadata/{prefix}:resource/datacite:identifier[@identifierType="DOI"]', namespaces=NS)
            if identifier is None:
                identifier = record.find(f'./oai:metadata/{prefix}:resource/datacite:identifier[@identifierType="URL"]', namespaces=NS)
            datestamp = record.find('./oai:header/oai:datestamp', namespaces=NS)

            if identifier is None or datestamp is None:
                raise ValueError(f'XML OAI-PMH record {record} without identifier or datestamp')

            additional_metadata = None
            if additional_dir and oai_id.text is not None:

                search_path_seg = oai_id_without_prefix.replace('/', '_')

                additional_file = list(additional_dir.rglob(f'*{search_path_seg}*'))

                #print(additional_file)

                if len(additional_file) == 1:
                    with open(additional_file[0]) as f2:
                        additional_metadata = f2.read()

            payload = {
                'record_identifier': oai_id_without_prefix,
                'datestamp': datestamp.text,
                'raw_metadata': ET.tostring(record, encoding='unicode'),
                'additional_metadata': additional_metadata,
                'harvest_url': harvest_url,
                'repo_code': repo_code,
                'harvest_run_id': harvest_run_id,
                'is_deleted': False
            }

            res = requests.post(f'http://{FASTAPI_ADDRESS}:{FASTAPI_PORT}/harvest_event', json=payload, timeout=TIMEOUT_FASTAPI)

            res.raise_for_status()

            print(identifier.text)
            print('+++++')
            count += 1
            if limit and count >= limit:
                break

    except Exception as e:
        print(f'An error occurred when creating harvest event: {e}', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


    completed = datetime.now(timezone.utc)

    try:
        res = requests.put(f'http://{FASTAPI_ADDRESS}:{FASTAPI_PORT}/harvest_run', json={
            'id': harvest_run_id,
            'success': True,
            'started_at': started.strftime(TIMESTAMP_FORMAT),
            'completed_at': completed.strftime(TIMESTAMP_FORMAT)
        }, timeout=TIMEOUT_FASTAPI)

        res.raise_for_status()

    except Exception as e:
        print(f'An error occurred when closing the harvest run: {e}', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise e

HARVEST_ENDPOINTS = [
    ('DANS', 'https://archaeology.datastations.nl/oai', Path('data/dans_arch/dans_arch.xml'), Path('doi_dataverse'), 200),
    #('DANS', 'https://ssh.datastations.nl/oai', Path('data/dans_soc/dans_soc.xml'), Path('doi_dataverse'), 500),
    #('DANS', 'https://lifesciences.datastations.nl/oai', Path('data/dans_life/dans_life.xml'), Path('doi_dataverse'), 500),
    #('DANS', 'https://phys-techsciences.datastations.nl/oai', Path('data/dans_phystec/dans_phystec.xml'), Path('doi_dataverse'), 500),
    #('DANS', 'https://dataverse.nl/oai', Path('data/dans_gen/dans_gen.xml'), Path('doi_dataverse'), 500),
    #('SWISS', 'https://www.swissubase.ch/oai-pmh/v1/oai', Path('doi_dataverse'), None),
    #('DABAR', 'https://dabar.srce.hr/oai/', Path('data/harvests_DABAR'), Path('data/harvests_DABAR_additional')),
    ('HAL', 'https://api.archives-ouvertes.fr/oai/hal', Path('data/hal/linked_research_outputs.xml'), Path('meta_hal'), 200),
    ('ZENODO', 'https://zenodo.org/oai2d', Path('data/zenodo/zenodo_parts.xml'), Path('meta_zenodo'), 200)
]

if __name__ == "__main__":
    for repo, harvest_url_repo, path, add, lim in HARVEST_ENDPOINTS:
        import_data(repo, harvest_url_repo, path, add, lim)
