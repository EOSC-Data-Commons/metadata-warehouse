"""
Scheduler entrypoint.

Executed periodically by CRON.
Workflow:
cron
   ↓
docker compose run --rm scheduler
   ↓
scheduler/run.py
   ↓
docker compose run --rm harvester <harvest_url>
   ↓
transform (harvest_run_id, index_name )
   ↓
indexing
"""

import logging
from logging.config import dictConfig

from config.logging_config import LOGGING_CONFIG
from scheduler.pipeline import run_pipeline

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


if __name__ == '__main__':
    logger.info('scheduler job started')

    run_pipeline()

    logger.info('scheduler job finished')
