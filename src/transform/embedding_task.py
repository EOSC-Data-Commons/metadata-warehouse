import os
from typing import Any

import psycopg
from celery import Task
from psycopg.rows import class_row

from config.postgres_config import PostgresConfig
from transform.celery_app_def import celery_app, logger
from utils.chunk_embedding_utils import (
    DATACITE_KEYS,
    RESOURCE_TYPES,
    SourceRecord,
    build_dataset_row,
    dataset_chunks,
    embed_chunks,
)

EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL')
if not EMBEDDING_MODEL:
    raise ValueError('Missing EMBEDDING_MODEL environment variable')

EMBED_API_KEY = os.environ.get('EMBED_API_KEY')
EMBED_API_URL = os.environ.get('EMBED_API_URL')


class EmbeddingTask(Task):  # type: ignore
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        self.postgres_config = PostgresConfig()


@celery_app.task(base=EmbeddingTask, bind=True, ignore_result=True)
def embed_batch(self: Any, record_ids: list[str]) -> Any:

    with psycopg.connect(
        **self.postgres_config.connection_params, row_factory=class_row(SourceRecord), autocommit=False
    ) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT 
        rec.id AS source_record_id,
        rec.url,
        rec.title,
        rec.resource_type,
        jsonb_build_object(
            {', '.join(f"'{key}', rec.datacite_json -> '{key}'" for key in DATACITE_KEYS)}
        ) AS datacite_json,
        rec.datestamp,
        rec.updated_at,
        repo.code AS repository_code,
        repo.name AS repository_name
        FROM records rec
        JOIN repositories repo ON rec.repository_id = repo.id
        WHERE rec.resource_type = ANY(%(resource_types)s)
        AND rec.datacite_json IS NOT NULL            
        AND rec.id = ANY(%(record_ids)s)
        """,
            {'resource_types': list(RESOURCE_TYPES), 'record_ids': record_ids},
        )

        records = cur.fetchall()

    dataset_rows = []
    chunks = []
    for record in records:
        dataset_row = build_dataset_row(record)
        dataset_row_chunks = dataset_chunks(dataset_row)

        dataset_rows.append(dataset_row)
        chunks.extend(dataset_row_chunks)

    # embed
    if EMBEDDING_MODEL and EMBED_API_KEY and EMBED_API_URL:
        embedding_model_name = EMBEDDING_MODEL.split('/')[-1]
        embedded = embed_chunks(chunks, EMBED_API_KEY, EMBED_API_URL, embedding_model_name, logger)

        logger.info(f'Dataset rows: {dataset_rows}')
        logger.info(f'Embedded chunks: {embedded}')
