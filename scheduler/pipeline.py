"""
Synchronous harvesting pipeline.

Flow
----
1. query transformer which endpoints should be harvested
2. run crawler sequentially for each endpoint
3. wait until all harvest runs are closed
4. fetch closed runs that require indexing
5. trigger transformer indexing
"""

import logging
import time

from scheduler.clients.transformer_client import (
    are_all_runs_closed,
    get_closed_run_ids,
    get_endpoints_to_harvest,
    trigger_index,
)
from scheduler.config import INDEX_NAME
from scheduler.runners.harvester_runner import run_harvester

logger = logging.getLogger(__name__)


# how often scheduler checks if harvesting finished
WAIT_INTERVAL_SECONDS = 300  # 5 minutes


def wait_until_runs_closed() -> None:
    """
    Poll transformer API until all harvest runs are closed.

    This prevents indexing before crawler has finished.
    """

    logger.info("waiting for harvest runs to close")
    attempt = 1

    while True:
        if are_all_runs_closed():
            logger.info("all harvest runs closed")
            return

        logger.info(
            "harvest still running - retry in %s seconds (attempt %s)",
            WAIT_INTERVAL_SECONDS,
            attempt,
        )

        time.sleep(WAIT_INTERVAL_SECONDS)
        attempt += 1


def run_pipeline(all_runs: bool = False) -> None:
    """
    Execute harvesting workflow.

    Parameters
    ----------
    all_runs : bool, optional
        If True, closed run retrieval is not limited to the last 6 days.
        Defaults to False.

    Raises
    ------
    RuntimeError
        if pipeline fails
    """

    logger.info("starting harvesting pipeline%s", " (all-runs mode)" if all_runs else "")
    harvest_urls = get_endpoints_to_harvest()

    if not harvest_urls and not all_runs:
        logger.info("no endpoints require harvesting")
        return

    logger.info("%s endpoints scheduled for harvesting", len(harvest_urls))

    for url in harvest_urls:
        logger.info("running harvester for %s", url)
        run_harvester(url)

    wait_until_runs_closed()

    logger.info("fetching closed runs requiring indexing")

    run_ids = get_closed_run_ids(all_runs=all_runs)

    if not run_ids:
        logger.info("no runs require indexing")
        return

    logger.info("trigger indexing for %s runs", len(run_ids))

    trigger_index(run_ids, INDEX_NAME)
    logger.info("pipeline finished successfully")

