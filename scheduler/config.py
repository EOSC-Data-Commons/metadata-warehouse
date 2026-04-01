"""Scheduler configuration"""

import os
from pathlib import Path

from dotenv import load_dotenv

# load .env from project root
BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(BASE_DIR / ".env")


TRANSFORMER_URL = os.getenv("TRANSFORMER_URL", "http://192.168.10.6:8080")

INDEX_NAME = os.getenv("INDEX_NAME", "test_datacite")
