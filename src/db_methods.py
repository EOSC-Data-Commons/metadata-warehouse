import logging
import os
from datetime import datetime, timezone
from json import JSONDecodeError
from logging.config import dictConfig
from typing import Any, Optional

import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from config.logging_config import LOGGING_CONFIG
from config.postgres_config import PostgresConfig
from tasks import add_file_metadata, transform_batch
from utils.queue_utils import HarvestEventQueue, detect_identifier_type

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

postgres_config: PostgresConfig = PostgresConfig()
connection_params = postgres_config.connection_params

DEFAULT_PROTOCOL = 'OAI-PMH'
DEFAULT_FORMAT = 'XML'

BATCH_SIZE_DEFAULT = 125
batch_size_raw = os.environ.get('CELERY_BATCH_SIZE', BATCH_SIZE_DEFAULT)

try:
    BATCH_SIZE = int(batch_size_raw)
except (TypeError, ValueError):
    raise ValueError('CELERY_BATCH_SIZE should be an integer')


class HealthGetResponse(BaseModel):
    status: str = Field(description='Server status')
    time: datetime = Field(description='Current daytime as UTC')


class IndexGetResponse(BaseModel):
    number_of_batches: int = Field(description='Number of batches created in Celery queue.')


class AdditionalMetadataParams(BaseModel):
    format: str
    endpoint: str
    protocol: str


class HarvestParams(BaseModel):
    metadata_prefix: str
    set: Optional[list[str]]
    additional_metadata_params: Optional[AdditionalMetadataParams]


class EndpointConfig(BaseModel):
    name: str
    harvest_url: str
    harvest_params: HarvestParams
    code: str
    protocol: str


class Config(BaseModel):
    endpoints_configs: list[EndpointConfig]


class HarvestEventCreateRequest(BaseModel):
    record_identifier: str
    datestamp: datetime
    raw_metadata: str  # XML
    additional_metadata: Optional[str] = None  # XML or JSON (stringified)
    harvest_url: str
    repo_code: str
    harvest_run_id: str
    is_deleted: bool


class HarvestEventCreateResponse(BaseModel):
    id: str


class HarvestRunCreateRequest(BaseModel):
    harvest_url: str


class HarvestRun(BaseModel):
    id: Optional[str] = Field(default=None, description='ID of the harvest run')

    status: Optional[str] = Field(default=None, description='Status of the harvest run: open|closed|failed')
    harvest_url: str
    from_date: Optional[datetime]
    until_date: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    should_be_harvested: bool = Field(
        description='Whether this endpoint should be harvested now, may based on is_active and harvest_schedule'
    )


class HarvestRunGetResponse(BaseModel):
    harvest_runs: Optional[list[HarvestRun]]


class HarvestRunCreateResponse(BaseModel):
    id: str = Field(description='ID of the new harvest run')
    from_date: Optional[datetime] = Field(None, description='From date for selective harvesting')
    until_date: datetime = Field(description='Until date for selective harvesting')
    endpoint_config: EndpointConfig = Field(description='Description of the endpoint used for harvesting')


class HarvestRunCloseRequest(BaseModel):
    id: str = Field(description='ID of the harvest run to close')
    success: bool = Field(description='Indicates if the harvest run was successful')
    started_at: datetime = Field(description='Start date of the harvest')
    completed_at: datetime = Field(description='End date of the harvest')


class HarvestRunCloseResponse(BaseModel):
    id: str = Field(description='ID of the closed harvest run')


class SchedulerRunsResponse(BaseModel):
    """
    Response returned by /scheduler/wait-for-completion endpoint.

    Attributes
    ----------
    all_closed : bool
        True when there are no harvest runs with status='open'.

        Both 'closed' and 'failed' statuses are treated as completed runs,
        meaning the scheduler can proceed to the next step of the workflow.
    """

    all_closed: bool


class SchedulerClosedRunsResponse(BaseModel):
    """
    Response returned by /scheduler/closed-runs endpoint.

    Attributes
    ----------
    harvest_run_ids : list[str]
        IDs of harvest runs that finished in the last 6 days.

        Includes runs with status:
        - 'closed'  -> completed successfully
        - 'failed'  -> completed with errors

        Failed runs are included because they are no longer actively running
        and should be processed further by Transfomer.
    """

    harvest_run_ids: list[str]


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


def create_harvest_run_in_db(harvest_url: str) -> HarvestRunCreateResponse:
    """
    Creates a new entry in harvest_runs and returns its id.

    :param harvest_url: The new entry to be created.
    """

    with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()
        # TODO: only allow one open harvest run per endpoint
        # TODO check (in one transaction):
        # - an open harvest run exists for the given endpoint
        # - only create a new harvest run if all previous are closed, if any

        # https://stackoverflow.com/questions/15710162/conditional-insert-into-statement-in-postgres/15710289
        res = cur.execute(
            """
            INSERT INTO harvest_runs
                (endpoint_id, status, from_date)
                select 
                (SELECT id FROM endpoints WHERE harvest_url = %s),
                'open',
                (SELECT until_date 
     FROM harvest_runs hr
     JOIN endpoints e ON hr.endpoint_id = e.id
     WHERE e.harvest_url = %s 
       AND hr.status = 'closed' 
     ORDER BY hr.until_date DESC 
     LIMIT 1)
            """,
            (harvest_url, harvest_url),
        )

        logger.debug(f'insert operation state: {res}')

        cur.execute(
            """SELECT hr.id, hr.from_date, hr.until_date,  e.name, e.harvest_url, e.harvest_params, e.protocol, r.code  
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
                    he.raw_metadata,
                    he.additional_metadata,
                    he.repo_code,
                    he.harvest_url,
                    DEFAULT_PROTOCOL,
                    DEFAULT_FORMAT,
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


def create_jobs_in_queue(harvest_run_id: str, index_name: str) -> int:
    """
    Creates and enqueues transformation jobs from harvest_events table.

    :param harvest_run_id: ID of the harvest run the harvest events belong to.
    :param index_name: Name of the OpenSearch index to use.
    :return: Number of batches scheduled for processing.
    """

    batch: list[HarvestEventQueue] = []
    tasks = 0
    offset = 0
    limit = BATCH_SIZE
    fetch = True

    logger.info(f'Preparing jobs for index: {index_name}')

    with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()
        while fetch:
            cur.execute(
                """
            SELECT he.id, 
            he.repository_id,
            r.code, 
            he.endpoint_id, 
            e.harvest_url,
            he.record_identifier, 
            (
                xpath('/oai:record', he.raw_metadata, '{{oai, http://www.openarchives.org/OAI/2.0/},{datacite, http://datacite.org/schema/kernel-4}}')
            )[1] AS record,
            he.additional_metadata,
            he.is_deleted,
            he.datestamp,
            e.harvest_params
        FROM harvest_events he
        JOIN harvest_runs hr ON he.harvest_run_id = hr.id 
        JOIN endpoints e ON he.endpoint_id = e.id
        JOIN repositories r ON he.repository_id = r.id
            WHERE harvest_run_id = %s and hr.status = 'closed' 
            ORDER BY he.id
            LIMIT %s
            OFFSET %s
            """,
                (harvest_run_id, limit, offset),
            )

            for doc in cur.fetchall():
                # https://www.psycopg.org/psycopg3/docs/basic/adapt.html#uuid-adaptation
                # https://docs.python.org/3/library/uuid.html#uuid.UUID
                # str(uuid) returns a string in the form 12345678-1234-5678-1234-567812345678 where the 32 hexadecimal digits represent the UUID.

                additional_metadata_API = (
                    doc.get('harvest_params', {}).get('additional_metadata_params', {}).get('endpoint')
                )

                additional_metadata_protocol = (
                    doc.get('harvest_params', {}).get('additional_metadata_params', {}).get('protocol')
                )

                batch.append(
                    HarvestEventQueue(
                        id=str(doc['id']),
                        xml=doc['record'],
                        repository_id=str(doc['repository_id']),
                        endpoint_id=str(doc['endpoint_id']),
                        record_identifier=doc['record_identifier'],
                        identifier_type=detect_identifier_type(doc['record_identifier']),
                        code=doc['code'],
                        harvest_url=doc['harvest_url'],
                        additional_metadata=doc['additional_metadata'],
                        additional_metadata_API=additional_metadata_API,
                        additional_metadata_protocol=additional_metadata_protocol,
                        is_deleted=doc['is_deleted'],
                        datestamp=doc['datestamp'].strftime('%Y-%m-%d %H:%M:%S.%f%z'),
                    )
                )

            if len(batch) == 0:
                # batch is empty
                break

            # https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#keeping-results
            logger.info(f'Putting batch of {len(batch)} in queue with offset {offset}')
            transform_batch.delay(batch, index_name)
            add_file_metadata.delay(batch)
            tasks += 1

            # increment offset by limit
            offset += limit
            # will be false if query returned fewer results than limit
            fetch = len(batch) == limit
            # fetch = False
            batch = []

    return tasks


def are_all_runs_closed_in_db() -> bool:
    """
    Check whether all harvest runs have finished processing.

    A run is considered finished when its status is:
    - 'closed'
    - 'failed'

    The scheduler should wait only for runs that are still actively executing,
    which are represented by status='open'.

    Returns
    -------
    bool
        True if there are no runs with status='open'.
        False if at least one run is still open.

    Notes
    -----
    Expected status values in harvest_runs table:
        ('open', 'closed', 'failed')

    Logic:
        EXISTS(status='open') -> scheduler must wait
        no open runs -> scheduler may continue
    """
    with psycopg.connect(**connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM harvest_runs
                WHERE status = 'open'
            ) AS has_open_runs
        """)

        result = cur.fetchone()
        if result is None:
            raise RuntimeError('Query returned no result')

        return not result['has_open_runs']
