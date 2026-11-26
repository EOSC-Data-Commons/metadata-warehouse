"""Check if the file DB can be looked up for the records of the dataset DB (used by the Airflow DAG
`warehouse_check_file_sync`).

The file metadata of a record is stored in `record_files` of the file DB and found with the pair
(`harvest_url`, `record_identifier`). The dataset DB identifies the endpoint of a record by `endpoint_id`, so this
module translates it to the harvest url of the endpoint and counts the matching `record_files` rows.

Every record is put in one bucket:

* `in_sync`: the extractor had input and there are file rows
* `possible_sync_issue`: the extractor had input and supports the provider, but there are no file rows
* `expected_gap`: no input for the extractor (no `records.additional_metadata`), no file rows
* `unexpected_files`: no input for the extractor, but there are file rows
* `unsupported_provider`: there is input, but the file extractor does not support the provider, no file rows

`possible_sync_issue` is a signal, not a proof: a provider can legitimately have no files for a record and a failing
extraction is only logged by the transform.

Both databases are only read.
"""

import logging
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

from config.postgres_config import PostgresConfig

logger = logging.getLogger(__name__)

# What `transform/file_meta_core.py` supports. Not imported from there: it imports datahugger, which only exists in the
# transform venv, not in the environment of the DAG tasks. Keep both in sync by hand.
# SWISS is crawled from the web and does not use `additional_metadata`.
SWISS_CODE = 'SWISS'
# These use `additional_metadata`. Dataverse endpoints are not found by code but by their additional metadata params.
EXTRACTOR_CODES = frozenset({'ZENODO', 'HAL', 'DABAR', 'DASCH', 'MDDB', 'FINBIF'})
DATAVERSE_PROTOCOL = 'DATAVERSE_API'

IN_SYNC = 'in_sync'
POSSIBLE_SYNC_ISSUE = 'possible_sync_issue'
EXPECTED_GAP = 'expected_gap'
UNEXPECTED_FILES = 'unexpected_files'
UNSUPPORTED_PROVIDER = 'unsupported_provider'
BUCKETS = (IN_SYNC, POSSIBLE_SYNC_ISSUE, EXPECTED_GAP, UNEXPECTED_FILES, UNSUPPORTED_PROVIDER)

_SELECT_ENDPOINTS = """
    SELECT e.id, e.harvest_url, rep.code, e.harvest_params
    FROM endpoints e
    JOIN repositories rep ON e.repository_id = rep.id
    WHERE cardinality(%s::text[]) = 0 OR e.harvest_url = ANY(%s::text[])
    ORDER BY rep.code, e.harvest_url
"""

# Keyset pagination on the unique key (endpoint_id, record_identifier): an index range scan whose cost does not grow
# with the position in the table. The content of additional_metadata (can be large) is not loaded, only if it exists.
_SELECT_RECORDS = """
    SELECT record_identifier,
           (additional_metadata IS NOT NULL AND btrim(additional_metadata) <> '') AS has_additional_metadata
    FROM records
    WHERE endpoint_id = %s AND record_identifier > %s
    ORDER BY record_identifier
    LIMIT %s
"""

_COUNT_FILES = """
    SELECT record_identifier, count(*) AS files
    FROM record_files
    WHERE harvest_url = %s AND record_identifier = ANY(%s::text[])
    GROUP BY record_identifier
"""


def extractor_support(code: str, harvest_params: dict[str, Any] | None) -> tuple[bool, bool]:
    """Mirrors the branches of `transform_filemetadata_batch_impl`.

    :return: (provider is supported by the file extractor, extractor needs `additional_metadata`)
    """
    if code == SWISS_CODE:
        return True, False

    additional_metadata_params = (harvest_params or {}).get('additional_metadata_params') or {}
    is_dataverse = bool(
        additional_metadata_params.get('endpoint') and additional_metadata_params.get('protocol') == DATAVERSE_PROTOCOL
    )

    return is_dataverse or code in EXTRACTOR_CODES, True


def classify_record(
    has_additional_metadata: bool, has_files: bool, supported: bool, uses_additional_metadata: bool
) -> str:
    """Bucket of one record, see the module docstring."""
    has_input = has_additional_metadata or not uses_additional_metadata

    if has_files:
        return IN_SYNC if has_input else UNEXPECTED_FILES
    if not has_input:
        return EXPECTED_GAP

    return POSSIBLE_SYNC_ISSUE if supported else UNSUPPORTED_PROVIDER


def file_db_config() -> PostgresConfig:
    """Config of the file DB. No fallback to the dataset DB (PostgresConfig would use it if FILE_DB is not set)."""
    file_db = os.environ.get('FILE_DB')
    if not file_db:
        raise ValueError('FILE_DB is not set in the environment')

    return PostgresConfig(db=file_db)


def list_endpoints(harvest_urls: list[str]) -> list[dict[str, Any]]:
    """The endpoints to check (all if `harvest_urls` is empty). An unknown harvest url raises a ValueError."""
    with psycopg.connect(**PostgresConfig().connection_params, row_factory=dict_row) as conn:
        rows = conn.execute(_SELECT_ENDPOINTS, (harvest_urls, harvest_urls)).fetchall()

    unknown = sorted(set(harvest_urls) - {row['harvest_url'] for row in rows})
    if unknown:
        raise ValueError(f'No endpoint with harvest url: {", ".join(unknown)}')

    endpoints = []
    for row in rows:
        supported, uses_additional_metadata = extractor_support(row['code'], row['harvest_params'])
        endpoints.append(
            {
                'endpoint_id': str(row['id']),
                'harvest_url': row['harvest_url'],
                'code': row['code'],
                'supported': supported,
                'uses_additional_metadata': uses_additional_metadata,
            }
        )

    return endpoints


def new_stats(endpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        'harvest_url': endpoint['harvest_url'],
        'code': endpoint['code'],
        'supported': endpoint['supported'],
        'records': 0,
        'with_additional_metadata': 0,
        'records_with_files': 0,
        'file_rows': 0,
        **{bucket: 0 for bucket in BUCKETS},
        # record identifiers of possible sync issues
        'samples': [],
    }


def update_stats(
    stats: dict[str, Any],
    endpoint: dict[str, Any],
    records: list[dict[str, Any]],
    file_counts: dict[str, int],
    sample_size: int,
) -> None:
    """Adds one batch of records (`record_identifier`, `has_additional_metadata`) and its file row counts to `stats`."""
    for record in records:
        identifier = record['record_identifier']
        files = file_counts.get(identifier, 0)

        bucket = classify_record(
            record['has_additional_metadata'], files > 0, endpoint['supported'], endpoint['uses_additional_metadata']
        )

        stats['records'] += 1
        stats['with_additional_metadata'] += int(record['has_additional_metadata'])
        stats['records_with_files'] += int(files > 0)
        stats['file_rows'] += files
        stats[bucket] += 1

        if bucket == POSSIBLE_SYNC_ISSUE and len(stats['samples']) < sample_size:
            stats['samples'].append(identifier)


def check_endpoint(endpoint: dict[str, Any], batch_size: int, sample_size: int) -> dict[str, Any]:
    """Counts the records of one endpoint and the matching file rows, in batches of `batch_size` records."""
    stats = new_stats(endpoint)

    with (
        psycopg.connect(**PostgresConfig().connection_params, row_factory=dict_row, autocommit=True) as datasets,
        psycopg.connect(**file_db_config().connection_params, row_factory=dict_row, autocommit=True) as files,
    ):
        datasets.read_only = True
        files.read_only = True

        last_identifier = ''
        while True:
            query = (endpoint['endpoint_id'], last_identifier, batch_size)
            records = datasets.execute(_SELECT_RECORDS, query).fetchall()
            if not records:
                break
            last_identifier = records[-1]['record_identifier']

            identifiers = [record['record_identifier'] for record in records]
            rows = files.execute(_COUNT_FILES, (endpoint['harvest_url'], identifiers)).fetchall()
            file_counts = {row['record_identifier']: row['files'] for row in rows}
            update_stats(stats, endpoint, records, file_counts, sample_size)

    logger.info(f'{endpoint["harvest_url"]}: checked {stats["records"]} records')
    return stats


def has_gaps(stats: dict[str, Any]) -> bool:
    return int(stats[POSSIBLE_SYNC_ISSUE]) > 0


def _percent(part: int, total: int) -> str:
    return f'{100 * part / total:.1f}%' if total else 'n/a'


def format_endpoint(stats: dict[str, Any]) -> str:
    lines = [
        f'{stats["code"]}  {stats["harvest_url"]}' + ('' if stats['supported'] else '  (file extractor: unsupported)'),
        f'  records: {stats["records"]}, with additional_metadata: {stats["with_additional_metadata"]}',
        f'  records with files: {stats["records_with_files"]} '
        f'({_percent(stats["records_with_files"], stats["records"])}), file rows: {stats["file_rows"]}',
        '  ' + ', '.join(f'{bucket}: {stats[bucket]}' for bucket in BUCKETS),
    ]
    if stats['samples']:
        lines.append(f'  examples of {POSSIBLE_SYNC_ISSUE}: {", ".join(stats["samples"])}')

    return '\n'.join(lines)


def format_report(results: list[dict[str, Any]], only_gaps: bool) -> str:
    """Report of all endpoints (only the ones with possible sync issues if `only_gaps`) and the total."""
    shown = [stats for stats in results if has_gaps(stats)] if only_gaps else results

    keys = ('records', 'records_with_files', 'file_rows', *BUCKETS)
    total = {key: sum(stats[key] for stats in results) for key in keys}
    blocks = [format_endpoint(stats) for stats in shown] or ['No endpoint with possible sync issues']
    blocks.append(
        f'TOTAL ({len(results)} endpoints): records: {total["records"]}, '
        f'records with files: {total["records_with_files"]} '
        f'({_percent(total["records_with_files"], total["records"])}), file rows: {total["file_rows"]}, '
        + ', '.join(f'{bucket}: {total[bucket]}' for bucket in BUCKETS)
    )

    return '\n\n'.join(blocks)
