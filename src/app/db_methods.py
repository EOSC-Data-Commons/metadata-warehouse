import os
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any, Optional

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from app.api_classes import (
    EndpointConfig,
    HarvestEventCreateRequest,
    HarvestEventCreateResponse,
    HarvestParams,
    HarvestRun,
    HarvestRunCloseRequest,
    HarvestRunCloseResponse,
    HarvestRunCreateResponse,
    HarvestRunGetResponse,
    InvalidUntilDateError,
)
from config.postgres_config import PostgresConfig
from logger.setup_logger import logger

postgres_config: PostgresConfig = PostgresConfig()
connection_params = postgres_config.connection_params

DEFAULT_PROTOCOL = 'OAI-PMH'
FORMAT_XML = 'XML'
FORMAT_JSON = 'JSON'


BATCH_SIZE_DEFAULT = 125
batch_size_raw = os.environ.get('CELERY_BATCH_SIZE', BATCH_SIZE_DEFAULT)

try:
    BATCH_SIZE = int(batch_size_raw)
except (TypeError, ValueError):
    raise ValueError('CELERY_BATCH_SIZE should be an integer')


def get_latest_harvest_run_in_db(
    harvest_url: Optional[str] = None,
    only_active: bool = False,
    respect_schedule: bool = False,
) -> HarvestRunGetResponse:
    """
    Returns endpoints and their latest harvest run (if any).

    Each result includes a `should_be_harvested` flag indicating whether
    the endpoint is active and its harvest_schedule interval has elapsed
    since the last run (or has never been run).

    Parameters
    ----------
    harvest_url : Optional[str]
        If provided, filters results to the single endpoint with this URL.
    only_active : bool
        If True, only return endpoints where is_active = TRUE.
    respect_schedule : bool
        If True, only return endpoints where the harvest_schedule interval
        has elapsed since the last harvest run's until_date.

    Returns
    -------
    HarvestRunGetResponse
        Contains a list of HarvestRun objects. Empty list if no endpoints
        match the given filters.
    """

    schedule_condition = """
    (
        hr.until_date IS NULL
        OR NOW() >= hr.until_date + e.harvest_schedule
    )
    """

    with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        filters: list[str] = []
        params: list[Any] = []

        if harvest_url is not None:
            filters.append('e.harvest_url = %s')
            params.append(harvest_url)

        if only_active:
            filters.append('e.is_active = TRUE')

        if respect_schedule:
            filters.append(schedule_condition)

        where_clause = ''
        if filters:
            where_clause = 'WHERE ' + ' AND '.join(filters)

        query = f"""
        SELECT
            e.harvest_url,
            e.is_active,
            e.harvest_schedule,
            hr.id,
            hr.status,
            hr.from_date,
            hr.until_date,
            hr.started_at,
            hr.completed_at,
            (
                e.is_active = TRUE
                AND {schedule_condition}
            ) AS should_be_harvested

        FROM endpoints e

        LEFT JOIN LATERAL (
            SELECT
                id,
                status,
                from_date,
                until_date,
                started_at,
                completed_at
            FROM harvest_runs
            WHERE endpoint_id = e.id
            ORDER BY until_date DESC
            LIMIT 1
        ) hr ON TRUE

        {where_clause}
        """

        cur.execute(query, params)
        rows = cur.fetchall()

        harvest_runs = [
            HarvestRun(
                id=str(r['id']) if r['id'] else None,
                status=r['status'],
                harvest_url=r['harvest_url'],
                from_date=r['from_date'],
                until_date=r['until_date'],
                started_at=r['started_at'],
                completed_at=r['completed_at'],
                should_be_harvested=r['should_be_harvested'],
            )
            for r in rows
        ]

        return HarvestRunGetResponse(harvest_runs=harvest_runs)


def create_harvest_run_in_db(harvest_url: str, until_date: datetime | None = None) -> HarvestRunCreateResponse:
    """
    Creates a new entry in harvest_runs and returns its id.

    :param harvest_url: The new entry to be created.
    :param until_date: Optional until date of the run (default: now). Allows to register an initial harvest from a dump
        taken at a given date, so that the next run harvests from that date.
    :raises InvalidUntilDateError: if until_date is in the future or earlier than the until date of the latest
        closed run.
    """

    with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        if until_date is not None:
            if until_date > datetime.now(timezone.utc):
                raise InvalidUntilDateError('until_date must not be in the future')

            cur.execute(
                """
                SELECT max(hr.until_date) AS latest_until_date
                FROM harvest_runs hr
                JOIN endpoints e ON hr.endpoint_id = e.id
                WHERE e.harvest_url = %s AND hr.status = 'closed'
                """,
                [harvest_url],
            )
            latest = cur.fetchone()
            latest_until_date = latest['latest_until_date'] if latest else None
            if latest_until_date is not None and until_date < latest_until_date:
                raise InvalidUntilDateError(
                    'until_date must not be earlier than the until date of the latest closed harvest run '
                    f'({latest_until_date.isoformat()})'
                )

        # TODO: only allow one open harvest run per endpoint
        # TODO check (in one transaction):
        # - an open harvest run exists for the given endpoint
        # - only create a new harvest run if all previous are closed, if any

        # https://stackoverflow.com/questions/15710162/conditional-insert-into-statement-in-postgres/15710289
        res = cur.execute(
            """
            INSERT INTO harvest_runs
                (endpoint_id, status, from_date, until_date)
                select 
                (SELECT id FROM endpoints WHERE harvest_url = %s),
                'open',
                (SELECT until_date 
     FROM harvest_runs hr
     JOIN endpoints e ON hr.endpoint_id = e.id
     WHERE e.harvest_url = %s 
       AND hr.status = 'closed' 
     ORDER BY hr.until_date DESC 
     LIMIT 1),
                COALESCE(%s::timestamptz, CURRENT_TIMESTAMP)
            """,
            (harvest_url, harvest_url, until_date),
        )

        logger.debug(f'insert operation state: {res}')

        cur.execute(
            """SELECT hr.id, hr.from_date, hr.until_date, e.name, e.harvest_url, e.harvest_params, e.protocol, r.code
                    FROM harvest_runs hr
                    JOIN endpoints e ON hr.endpoint_id = e.id
                    JOIN repositories r ON e.repository_id = r.id
                    WHERE hr.status = 'open' and e.harvest_url = %s
                    LIMIT 1
                    """,
            [harvest_url],
        )
        new_harvest_run = cur.fetchone()

        if new_harvest_run is None:
            raise Exception(f'Harvest run could not be created')

        logger.debug(f'{new_harvest_run}')

        return HarvestRunCreateResponse(
            id=str(new_harvest_run['id']),
            from_date=new_harvest_run['from_date'],
            until_date=new_harvest_run['until_date'],
            endpoint_config=EndpointConfig(
                name=new_harvest_run['name'],
                harvest_url=new_harvest_run['harvest_url'],
                code=new_harvest_run['code'],
                protocol=new_harvest_run['protocol'],
                harvest_params=HarvestParams(
                    metadata_prefix=new_harvest_run['harvest_params'].get('metadata_prefix'),
                    set=new_harvest_run['harvest_params'].get('set'),
                    additional_metadata_params=new_harvest_run['harvest_params'].get('additional_metadata_params'),
                ),
            ),
        )


def close_harvest_run_in_db(
    harvest_run: HarvestRunCloseRequest,
) -> HarvestRunCloseResponse:
    with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        state = 'closed' if harvest_run.success else 'failed'

        cur.execute(
            """
            UPDATE harvest_runs
            SET status = %s, started_at = %s, completed_at = %s 
            WHERE id = %s and status = 'open'
        """,
            (state, harvest_run.started_at, harvest_run.completed_at, harvest_run.id),
        )

        cur.execute(
            """
            SELECT id 
            FROM harvest_runs
            WHERE id = %s and status != 'open'
        """,
            [harvest_run.id],
        )

        closed_harvest_run = cur.fetchone()

        if closed_harvest_run is None:
            raise Exception(f'Harvest run could not be closed')

        return HarvestRunCloseResponse(id=harvest_run.id)


def create_harvest_events_bulk_in_db(
    harvest_events: list[HarvestEventCreateRequest],
) -> list[HarvestEventCreateResponse]:
    """
    Creates multiple records in table harvest_events in a single transaction.
    """
    with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        cur.executemany(
            """
            INSERT INTO harvest_events 
                (record_identifier,
                datestamp, 
                raw_metadata,
                raw_metadata_json,
                additional_metadata,
                repository_id, 
                endpoint_id,  
                metadata_protocol,
                metadata_format,
                harvest_run_id,
                is_deleted
                ) 
            VALUES ( 
                %s,
                %s, 
                XMLPARSE(DOCUMENT %s), 
                %s::jsonb,
                %s,
                (SELECT id from repositories WHERE code=%s),
                (SELECT id from endpoints WHERE harvest_url=%s), 
                %s,
                %s,
                (SELECT id FROM harvest_runs WHERE id = %s and status = 'open'),
                %s
                )
            RETURNING id
            """,
            [
                (
                    he.record_identifier,
                    he.datestamp,
                    # exactly one of raw_metadata (XML) and raw_metadata_json (JSON) is set, the DB checks the syntax
                    None if he.is_json else he.raw_metadata,
                    he.raw_metadata if he.is_json else None,
                    he.additional_metadata,
                    he.repo_code,
                    he.harvest_url,
                    DEFAULT_PROTOCOL,
                    FORMAT_JSON if he.is_json else FORMAT_XML,
                    he.harvest_run_id,
                    he.is_deleted,
                )
                for he in harvest_events
            ],
            returning=True,
        )

        ids = []
        for _ in harvest_events:
            row = cur.fetchone()
            if row is None:
                raise Exception(f'Expected id for harvest event but got None')
            ids.append(row['id'])
            cur.nextset()

        if len(ids) != len(harvest_events):
            raise Exception(f'Only {len(ids)}/{len(harvest_events)} harvest events were registered')

        return [HarvestEventCreateResponse(id=str(id)) for id in ids]


def get_config_from_db() -> list[EndpointConfig]:
    """
    Returns the config for the available endpoints.
    """
    endpoints: list[EndpointConfig] = []

    try:
        with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
            cur = conn.cursor()

            cur.execute("""
SELECT 
    e.name, 
    e.harvest_url, 
    e.harvest_params, 
    e.protocol, 
    r.code
FROM endpoints e
JOIN repositories r ON e.repository_id = r.id
            """)
            for doc in cur.fetchall():
                endpoints.append(
                    EndpointConfig(
                        name=doc['name'],
                        harvest_url=doc['harvest_url'],
                        code=doc['code'],
                        protocol=doc['protocol'],
                        harvest_params=HarvestParams(
                            metadata_prefix=doc['harvest_params'].get('metadata_prefix'),
                            set=doc['harvest_params'].get('set'),
                            additional_metadata_params=doc['harvest_params'].get('additional_metadata_params'),
                        ),
                    )
                )

        return endpoints
    except JSONDecodeError as e:
        logger.exception(f'Parsing of harvest_params failed: {e}')
        raise HTTPException(status_code=500, detail='Reading config failed.')
    except Exception as e:
        logger.exception(f'An error occurred when reading config: {e}')
        raise HTTPException(status_code=500, detail=str(e))
