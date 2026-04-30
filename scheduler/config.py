"""Scheduler configuration"""

import os
from pathlib import Path

from dotenv import load_dotenv

# load .env from project root
BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(BASE_DIR / '.env')


WAREHOUSE_API_URL = os.getenv('WAREHOUSE_API_URL', 'http://transform:80')
INDEX_NAME = os.getenv('INDEX_NAME', 'test_datacite')
