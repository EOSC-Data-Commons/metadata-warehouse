from typing import Any


def split_by_dependency(runs: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Returns the harvest urls that should be harvested now as (independent, dependent).

    `runs` are the entries of `GET /harvest_run`. Endpoints with a `depends_on_endpoint_id` have to be harvested
    after all independent endpoints, so their master endpoints (e.g. HAL before Zenodo) have a chance to finish first.
    The order within each group is kept.
    """
    due = [run for run in runs if run.get('should_be_harvested') and run.get('harvest_url') is not None]
    independent = [run['harvest_url'] for run in due if run.get('depends_on_endpoint_id') is None]
    dependent = [run['harvest_url'] for run in due if run.get('depends_on_endpoint_id') is not None]
    return independent, dependent
