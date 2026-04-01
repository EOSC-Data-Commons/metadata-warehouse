"""
Client for transformer scheduler endpoints.

Responsibilities:
- determine which endpoints require harvesting
- verify harvest completion
- trigger indexing
"""

import logging
from typing import Any, Dict

import requests

from scheduler.config import TRANSFORMER_URL

logger = logging.getLogger(__name__)


def get_endpoints_to_harvest() -> list[str]:
    """
    Fetch harvest URLs of endpoints that should be harvested now.

    Queries the transformer API and filters results by the
    `should_be_harvested` flag returned per endpoint, which reflects
    whether the endpoint is active and its harvest_schedule has elapsed.

    Returns
    -------
    list[str]
        List of harvest URLs that require harvesting now.
        Empty list if no endpoints meet the criteria.

    Raises
    ------
    requests.HTTPError
        If the transformer service returns a non-success response.
    requests.RequestException
        If the request fails due to network issues or timeout.
    """
    logger.info("requesting endpoints to harvest")

    r = requests.get(
        f"{TRANSFORMER_URL}/harvest_run",
        params={"only_active": True, "respect_schedule": True},
        timeout=30,
    )

    r.raise_for_status()
    data = r.json()
    runs = data.get("harvest_runs") or []

    urls = [
        run["harvest_url"]
        for run in runs
        if run.get("should_be_harvested") and run["harvest_url"] is not None
    ]

    logger.info("%s endpoints require harvesting", len(urls))

    return urls


def are_all_runs_closed() -> bool:
    """
    Check if all harvest runs are completed.

    Returns
    -------
    bool
        True if no open harvest run exists
    """

    r = requests.post(f"{TRANSFORMER_URL}/scheduler/wait-for-completion", timeout=30)

    r.raise_for_status()

    data: Dict[str, Any] = r.json()
    result = bool(data["all_closed"])

    logger.debug("all runs closed = %s", result)

    return result


def get_closed_run_ids() -> list[str]:
    """
    Fetch harvest runs closed in the last days.

    Returns
    -------
    list[str]
        harvest_run ids
    """

    logger.info("requesting closed runs")
    r = requests.get(f"{TRANSFORMER_URL}/scheduler/closed-runs", timeout=30)

    r.raise_for_status()
    data: Dict[str, Any] = r.json()
    run_ids = [str(x) for x in data.get("harvest_run_ids", [])]

    logger.info("%s closed runs found", len(run_ids))

    return run_ids


def trigger_index(run_ids: list[str], index_name: str) -> None:
    """
    Trigger transformation/indexing.

    Parameters
    ----------
    run_ids : list[str]
        harvest run identifiers
    index_name : str
        OpenSearch index name
    """

    for run_id in run_ids:
        logger.info("trigger index for run %s", run_id)

        r = requests.get(
            f"{TRANSFORMER_URL}/index",
            params={"harvest_run_id": run_id, "index_name": index_name},
            timeout=6000,
        )

        r.raise_for_status()
