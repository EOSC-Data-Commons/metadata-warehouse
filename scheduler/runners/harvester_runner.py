"""
Runs metadata crawler synchronously via docker compose.
Scheduler just calls the harvester container as an external process.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def run_harvester(harvest_url: str) -> None:
    """
    Execute crawler synchronously.

    Parameters
    ----------
    harvest_url : str
        OAI-PMH endpoint URL
    """

    logger.info("running crawler for %s", harvest_url)

    subprocess.run(
        [
            "docker", "run",
            "--rm",
            "--network", "metadata-warehouse_warehouse-backend",
            "--env-file", "/app/.env",
            "-v", "metadata-warehouse_harvester-logs:/app/logs",
            "ghcr.io/eosc-data-commons/metadata-crawlers:latest",
            harvest_url,
        ],
        check=True,
    )

    logger.info("crawler finished for %s", harvest_url)
