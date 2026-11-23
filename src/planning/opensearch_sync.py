"""Sync the `records` table to a new OpenSearch index (used by the Airflow DAG `warehouse_opensearch_sync_index`).

Nothing is calculated here: `records.datacite_json` already holds the normalized document and `records.embeddings` the
embedding, which is exactly what the transform wrote to OpenSearch. The repository code and the harvest url are
read from the repository and the endpoint of the record. The table is only read, never written.
"""

import json
import logging
from pathlib import Path
from typing import Any

import psycopg
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
from psycopg.rows import dict_row

from config.opensearch_config import OpenSearchConfig
from config.postgres_config import PostgresConfig

logger = logging.getLogger(__name__)

# <root>/src/planning/opensearch_sync.py -> <root>/config/opensearch_mapping.json (independent of the working directory)
MAPPING_PATH = Path(__file__).resolve().parents[2] / 'config' / 'opensearch_mapping.json'

# Keyset pagination: records.id is the primary key, so `id > last_id ORDER BY id LIMIT n` is an index range scan
# whose cost does not grow with the position in the table (in contrast to OFFSET).
_SELECT_BATCH = """
    SELECT r.id,
           r.record_identifier,
           r.datacite_json,
           r.embeddings,
           rep.code,
           e.harvest_url
    FROM records r
    JOIN endpoints e ON r.endpoint_id = e.id
    JOIN repositories rep ON r.repository_id = rep.id
    WHERE r.id > %s
    ORDER BY r.id
    LIMIT %s
"""


def _client() -> OpenSearch:
    opensearch_config = OpenSearchConfig()
    return OpenSearch(
        hosts=[{'host': opensearch_config.host, 'port': opensearch_config.port}],
        http_auth=None,
        use_ssl=False,
        logger=logger,
    )


def create_index(index_name: str, embedding_dims: int) -> None:
    """Creates the index with the mapping of `config/opensearch_mapping.json`. Fails if the index already exists."""
    client = _client()
    try:
        if client.indices.exists(index=index_name):
            raise ValueError(f'Index {index_name} already exists in OpenSearch. Delete it or choose another name.')

        with open(MAPPING_PATH) as f:
            mapping = json.load(f)
        mapping['mappings']['properties']['emb']['dimension'] = embedding_dims

        client.indices.create(index=index_name, body=mapping)
        logger.info(f'Created index {index_name} (embedding dimension {embedding_dims})')
    finally:
        client.close()


def row_to_source(row: dict[str, Any]) -> dict[str, Any] | None:
    """OpenSearch document of a records row, same structure as in `transform_batch_impl` (reuse_embeddings).

    :return: the document, or None if the record has no `datacite_json` (nothing to index).
    """
    if row['datacite_json'] is None:
        return None

    source = {
        **row['datacite_json'],
        'emb': row['embeddings'],
        '_repo': row['code'],
        '_harvest_url': row['harvest_url'],
        '_record_identifier': row['record_identifier'],
    }

    # remove _additional_metadata if present
    source.pop('_additional_metadata', None)

    return source


def to_bulk_actions(sources: list[dict[str, Any]], index_name: str) -> list[dict[str, Any]]:
    """Bulk actions for OpenSearch, the same as `utils.embedding_utils.preprocess_batch` (the _id is the url).

    Not imported from there: that module imports fastembed, which only exists in the transform venv, not in the
    environment of this task.
    """
    return [{'_op_type': 'index', '_id': source['url'], '_index': index_name, '_source': source} for source in sources]


def sync_records(index_name: str, batch_size: int) -> int:
    """Indexes all rows of the records table in OpenSearch, in batches of `batch_size` rows.

    The index must exist. Documents are indexed by id (the url), so running this again is harmless.

    :return: number of documents indexed.
    """
    if batch_size < 1:
        raise ValueError(f'batch_size must be >= 1, got {batch_size}')

    client = _client()
    indexed = 0
    skipped = 0
    last_id = ''  # smaller than every id

    try:
        # autocommit: no transaction stays open during the whole (long) sync
        with psycopg.connect(**PostgresConfig().connection_params, row_factory=dict_row, autocommit=True) as conn:
            while True:
                rows = conn.execute(_SELECT_BATCH, (last_id, batch_size)).fetchall()
                if not rows:
                    break
                last_id = rows[-1]['id']

                sources: list[dict[str, Any]] = []
                for row in rows:
                    source = row_to_source(row)
                    if source is None:
                        skipped += 1
                        logger.warning(f'Skipping record {row["id"]}: no datacite_json')
                    else:
                        sources.append(source)

                if sources:
                    # raises BulkIndexError if documents are rejected, which fails the task
                    success: int
                    success, _ = bulk(client, to_bulk_actions(sources, index_name))
                    indexed += success

                logger.info(f'Synced up to record {last_id}: {indexed} documents indexed, {skipped} skipped')
    finally:
        client.close()

    return indexed
