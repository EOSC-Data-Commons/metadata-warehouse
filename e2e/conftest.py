"""Environment for the e2e run, applied before the test module imports anything from `transform`.

The jobs read their configuration at import time (EMBEDDING_MODEL), and these tests call them in
process rather than through the API, so .env has to be loaded before that import rather than at the
top of test_e2e.py. pytest imports conftest first, which is what makes the ordering reliable.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / '.env')

# The same model the containers use, so a local run reuses their download instead of fetching it
os.environ.setdefault('FASTEMBED_CACHE_DIR', str(REPO_ROOT / '.cache' / 'fastembed'))

# docker-compose.yml gives the containers POSTGRES_USER and the service hostnames; a host process
# running the same jobs gets neither, so stand in for compose here. PostgresConfig and
# OpenSearchConfig fall back to the container names, which do not resolve outside the network.
if admin := os.environ.get('POSTGRES_ADMIN'):
    os.environ.setdefault('POSTGRES_USER', admin)
for name in ('POSTGRES_ADDRESS', 'OPENSEARCH_ADDRESS'):
    if not os.environ.get(name):
        os.environ[name] = '127.0.0.1'
