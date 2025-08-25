#!/usr/bin/env python3

import argparse
import json
import os
import sys
from typing import Optional
import xmltodict
from pathlib import Path
from multiprocessing import Pool, cpu_count
from jsonschema import validate
from jsonschema.exceptions import ValidationError

# setting path
sys.path.append("..")
sys.path.append("../..")

from src.utils.normalize_datacite_json import normalize_datacite_json

def transform_record(filepath: Path, output_dir: Path, normalize: bool, schema: Optional[dict]):
    try:
        with open(filepath) as f:
            converted = xmltodict.parse(f.read(), process_namespaces=True)

        if normalize:
            metadata = converted['http://www.openarchives.org/OAI/2.0/:record'][
                'http://www.openarchives.org/OAI/2.0/:metadata']

            if 'http://datacite.org/schema/kernel-4:resource' in metadata:
                resource = metadata['http://datacite.org/schema/kernel-4:resource']
            else:
                # HAL
                resource = metadata['http://www.openarchives.org/OAI/2.0/:resource']

            normalized = normalize_datacite_json(resource)

            if schema is not None:
                validate(instance=normalized, schema=schema)

            with open(f'{output_dir}/{filepath.name}.json', 'w') as f:
                f.write(json.dumps(normalized))
        else:
            with open(f'{output_dir}/{filepath.name}.json', 'w') as f:
                f.write(json.dumps(converted))
    except ValidationError as e:
        print(f'Validation failed for {filepath}: {e.message}', file=sys.stderr)
    except Exception as e:
        print(f'Transformation failed for {filepath}: {e}', file=sys.stderr)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', help='input directory', type=str)
    parser.add_argument('-o', help='output directory', type=str)
    parser.add_argument('-s', help='path to schema file if normalized output should be validated (requires flag -n)', type=str)
    parser.add_argument('-n', help='If set, output JSON is normalized', action='store_true')

    args = parser.parse_args()

    if args.i is None or not os.path.isdir(args.i) or args.o is None or not os.path.isdir(args.o) or (args.s and not os.path.isfile(args.s)):
        parser.print_help()
        exit(1)

    files: list[Path] = (list(Path(args.i).rglob("*.xml")))

    schema = None
    if args.s is not None:
        with open(args.s) as f:
            schema = json.load(f)

    with Pool(processes=cpu_count()) as p:
        p.starmap(transform_record, map(lambda file: (file, args.o, args.n, schema), files))
