#!/usr/bin/env -S uv run --script

import pgsql
from dotenv import load_dotenv
import os
import xmltodict
import json
import sys

# setting path
sys.path.append("..")
sys.path.append("../..")

from src.utils.normalize_datacite_json import normalize_datacite_json

load_dotenv()

user = os.environ['POSTGRES_ADMIN']
pw = os.environ['POSTGRES_PASSWORD']

with pgsql.Connection(('localhost', 5432), user, pw, tls = False) as db:
    #print(db)

    with db.prepare("""
    SELECT (xpath('/oai:record/oai:metadata', info, '{{oai, http://www.openarchives.org/OAI/2.0/},{datacite, http://datacite.org/schema/kernel-4}}'))[1] AS root
FROM raw
    LIMIT 1000;
    """) as docs:

        all_rows = docs()
        #print(len(all_rows))

        for doc in all_rows():
            print(json.dumps(normalize_datacite_json(xmltodict.parse(doc.root, process_namespaces=True)['http://www.openarchives.org/OAI/2.0/:metadata'][
            'http://datacite.org/schema/kernel-4:resource'])))

