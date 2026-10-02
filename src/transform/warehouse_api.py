"""Client for the transform API's scheduler endpoints, used by the harvest pipeline DAG.

The DAG talks to the API rather than to postgres for these three queries so the harvest_schedule
logic (which endpoint is due, which run counts as closed) stays defined in one place, next to the
tables it reads.
"""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

# `or`, not a get() default: compose passes the variable through as an empty string when unset
WAREHOUSE_API_URL = os.environ.get('WAREHOUSE_API_URL') or 'http://transform:80'
TIMEOUT = 30


def order_runs_by_dependency(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return harvest runs in execution order.

    Endpoints with no dependency are triggered first. Endpoints with a
    non-null `depends_on_endpoint_id` are triggered after all independent
    endpoints so their master endpoints, for example HAL before Zenodo, have
    a chance to finish harvesting before the dependent crawler opens its run.

    The function uses a stable partition instead of computing a full
    dependency graph: the database prevents direct self-dependency, and the
    current requirement is only to defer configured dependent endpoints to
    the end of the same batch.
    """

    independent_runs = [run for run in runs if run.get('depends_on_endpoint_id') is None]
    dependent_runs = [run for run in runs if run.get('depends_on_endpoint_id') is not None]

    return independent_runs + dependent_runs


def get_endpoints_to_harvest() -> list[str]:
    """
    Fetch harvest URLs of endpoints that should be harvested now.

    Queries the transform API and filters results by the `should_be_harvested`
    flag returned per endpoint, which reflects whether the endpoint is active
    and its harvest_schedule has elapsed. The selected endpoints are ordered so
    independent endpoints run first and endpoints with a non-null
    `depends_on_endpoint_id` run at the end of the batch.

    Returns
    -------
    list[str]
        List of harvest URLs that require harvesting now.
        Empty list if no endpoints meet the criteria.

    Raises
    ------
    requests.HTTPError
        If the transform service returns a non-success response.
    requests.RequestException
        If the request fails due to network issues or timeout.
    """
    logger.info('requesting endpoints to harvest')

    r = requests.get(
        f'{WAREHOUSE_API_URL}/harvest_run',
        params={'only_active': True, 'respect_schedule': True},
        timeout=TIMEOUT,
    )

    r.raise_for_status()
    data = r.json()
    runs = data.get('harvest_runs') or []

    runs_to_harvest = [run for run in runs if run.get('should_be_harvested') and run.get('harvest_url') is not None]
    ordered_runs = order_runs_by_dependency(runs_to_harvest)
    urls = [run['harvest_url'] for run in ordered_runs]

    logger.info('%s endpoints require harvesting', len(urls))

    return urls


def are_all_runs_closed() -> bool:
    """
    Check if all harvest runs are completed.

    Returns
    -------
    bool
        True if no open harvest run exists
    """

    r = requests.post(f'{WAREHOUSE_API_URL}/scheduler/wait-for-completion', timeout=TIMEOUT)

    r.raise_for_status()

    data: dict[str, Any] = r.json()
    result = bool(data['all_closed'])

    logger.debug('all runs closed = %s', result)

    return result


def get_closed_run_ids(*, all_runs: bool = False) -> list[str]:
    """
    Fetch harvest runs closed in the last days.

    Parameters
    ----------
    all_runs : bool, optional
        If True, fetches runs from any time, not just the last 6 days.
        Defaults to False.

    Returns
    -------
    list[str]
        harvest_run ids
    """

    logger.info('requesting closed runs%s', ' (all time)' if all_runs else '')
    r = requests.get(
        f'{WAREHOUSE_API_URL}/scheduler/closed-runs',
        params={'all_runs': all_runs},
        timeout=TIMEOUT,
    )

    r.raise_for_status()
    data: dict[str, Any] = r.json()
    run_ids = [str(x) for x in data.get('harvest_run_ids', [])]

    logger.info('%s closed runs found', len(run_ids))

    return run_ids
