#!/usr/bin/env -S uv run --script

import argparse
import json
import os
import sys
from typing import Optional, Any
import xmltodict
from pathlib import Path
from multiprocessing import Pool, cpu_count
from jsonschema import validate
from jsonschema.exceptions import ValidationError
import traceback
from lxml import etree as ET

# setting path
sys.path.append("..")
sys.path.append("../..")

from src.utils.normalize_datacite_json import normalize_datacite_json
from src.utils.handle_xml import detect_metadata_namespace, detect_payload_namespace, preprocess_xml, OAI, get_resource

def transform_record(filepath: Path, output_dir: Path, normalize: bool, schema: Optional[dict[Any, Any]], perform_validation: bool) -> None:
    try:
        with open(filepath, encoding="utf-8") as f:
            contents = f.read()

        root = ET.fromstring(contents.encode('utf-8'))

        metadata_ns = detect_metadata_namespace(root)
        payload_ns = detect_payload_namespace(root)

        contents = preprocess_xml(root)
        converted = xmltodict.parse(contents, process_namespaces=True)

        if normalize:
            metadata = converted[f'{OAI}:record'][f'{OAI}:metadata']

            result = get_resource(metadata, metadata_ns, payload_ns)

            if result is None:
                raise ValueError(f"Could not detect metadata namespace in {filepath}")

            resource, metadata_namespace_for_access = result

            normalized = normalize_datacite_json(resource, metadata_namespace_for_access)

            if schema is not None and perform_validation:
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
        traceback.print_exc()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', help='input directory', type=str, required=True)
    parser.add_argument('-o', help='output directory', type=str, required=True)
    parser.add_argument('-s', help='path to schema file if normalized output should be validated (requires flag -n)', type=str)
    parser.add_argument('-n', help='If set, output JSON is normalized', action='store_true')
    parser.add_argument('-v', help='If set, output JSON is validated', action='store_true')

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
        p.starmap(transform_record, map(lambda file: (file, args.o, args.n, schema, args.v), files))
