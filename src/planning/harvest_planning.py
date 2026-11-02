"""Planning of the harvesting (used by the Airflow DAG `harvest_and_index`).

Replaces the endpoint selection (`GET /harvest_run`) and the closed-runs lookup (`GET /scheduler/closed-runs`) of the
custom scheduler.
"""

import psycopg
import requests
from psycopg.rows import dict_row

from config.postgres_config import PostgresConfig
from planning.ordering import split_by_dependency


def get_endpoints_to_harvest(warehouse_api_url: str) -> tuple[list[str], list[str]]:
    """Harvest urls of the endpoints that are due, as (independent, dependent)."""
    response = requests.get(
        f'{warehouse_api_url}/harvest_run',
        params={'only_active': True, 'respect_schedule': True},
        timeout=30,
    )
    response.raise_for_status()
    return split_by_dependency(response.json().get('harvest_runs') or [])


def db_now_iso() -> str:
    """Current time of the database server (used as reference to find the runs harvested afterwards)."""
    with psycopg.connect(**PostgresConfig().connection_params) as conn:
        row = conn.execute('SELECT now()').fetchone()
        assert row is not None
        return row[0].isoformat()  # type: ignore[no-any-return]


def find_closed_runs(harvest_urls: list[str] | None, completed_since: str | None) -> list[dict[str, str]]:
    """Closed harvest runs, oldest first.

    :param harvest_urls: only runs of these endpoints (None: all endpoints)
    :param completed_since: only runs completed at or after this time, ISO format (None: all runs)
    """
    conditions = ["hr.status = 'closed'"]
    params: list[object] = []
    if harvest_urls is not None:
        conditions.append('e.harvest_url = ANY(%s)')
        params.append(harvest_urls)
    if completed_since is not None:
        conditions.append('hr.completed_at >= %s::timestamptz')
        params.append(completed_since)

    query = f"""
        SELECT hr.id, e.harvest_url
        FROM harvest_runs hr
        JOIN endpoints e ON e.id = hr.endpoint_id
        WHERE {' AND '.join(conditions)}
        ORDER BY hr.completed_at
    """  # noqa: S608 (only fixed conditions are formatted in, values are passed as parameters)

    with psycopg.connect(**PostgresConfig().connection_params, row_factory=dict_row) as conn:
        rows = conn.execute(query, params).fetchall()
    return [{'harvest_run_id': str(row['id']), 'harvest_url': row['harvest_url']} for row in rows]
