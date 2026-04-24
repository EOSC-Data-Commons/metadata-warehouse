"""
Scheduler entrypoint.

Executed periodically by CRON.
Workflow:
cron
   ↓
docker compose run --rm scheduler [--all-runs]
   ↓
scheduler/run.py
   ↓
docker compose run --rm harvester <harvest_url>
   ↓
transform (harvest_run_id, index_name)
   ↓
indexing
"""

import argparse
import logging
from logging.config import dictConfig

from config.logging_config import LOGGING_CONFIG
from scheduler.pipeline import run_pipeline

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheduler pipeline entrypoint")
    parser.add_argument(
        "--all-runs",
        action="store_true",
        default=False,
        help="Retrieve closed runs from any time, not just the last 6 days",
    )
    args = parser.parse_args()

    logger.info("scheduler job started")

    run_pipeline(all_runs=args.all_runs)

    logger.info("scheduler job finished")
    
