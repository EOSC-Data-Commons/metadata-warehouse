#!/usr/bin/env -S uv run --script
"""Index datasets from datasetDB into appDB for hybrid search in postgres.

Source and target are different servers, so the diff is done in python, not in SQL. Per batch of
records, so a run is resumable and incremental:
  1. select the records in datasetDB that are missing or outdated in appDB
  2. build the normalized appDB dataset row from records.datacite_json
  3. split the text into named chunks (title, keywords, description) and embed them
  4. upsert the rows and their embeddings in appDB

Runs as a celery task (transform.tasks.index_datasets, enqueued after a harvest's transformation
batches) and as a CLI from a checkout, where --source-host/--target-host allow reading datasetDB on
one server while writing appDB on another:

    PYTHONPATH=src uv run python -m transform.index_datasets --count
    PYTHONPATH=src uv run python -m transform.index_datasets --limit 8000 --target-host 127.0.0.1
    PYTHONPATH=src uv run python -m transform.index_datasets --endpoint egi --target-host 127.0.0.1

SOURCE_ENV_FILE does the same for every run of a dev checkout, reading the source from .staging.env
while the target stays local. Whichever servers a run resolved are printed when it starts. The API
keys some endpoints need come from keys.env (see keys.env.template), which the celery service loads.

A run verifies nothing by default. Two checks are available on request, both exiting non zero on a
mismatch so they can gate a re-index.

Before trusting a new endpoint, or a raised batch_size in embed.py, check that it answers a batch
the way it answers the same texts one at a time:

    PYTHONPATH=src uv run python -m transform.index_datasets --check-batching 32 --endpoint egi

Expect a worst similarity of ~1.000000. Anything below VERIFY_MIN_COSINE means that batch_size is
too high for that endpoint, and every search built on its vectors is quietly degraded.

To check what is already stored, rather than the endpoint:

    PYTHONPATH=src uv run python -m transform.index_datasets --verify 200 --target-host 127.0.0.1

Samples N chunks by md5(record_url) rather than heap order, since the rows inserted first are the
correct ones and a spot check of those looks fine while the rest of the table is broken. Each
chunk_text is re-embedded one at a time and compared to its stored vector; expect ~100% at ~1.0000.
"""

import argparse
import json
import logging
import os
import re
import signal
import sys
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any, LiteralString, cast

import psycopg
from dotenv import dotenv_values, load_dotenv
from psycopg import sql
from psycopg.rows import class_row

from .embed import (
    API_ENDPOINTS,
    DEFAULT_ENDPOINT,
    EMBEDDING_MODEL,
    VERIFY_MIN_COSINE,
    ApiEmbeddings,
    build_embedder,
    cosine_similarity,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parents[2]

# Only present in a checkout, so a dev run needs nothing exported (compose sets the containers up)
DEV_ENV_FILES = (REPO_ROOT / '.env', REPO_ROOT / 'keys.env')

# DEV ONLY: comment out to read datasetDB from the POSTGRES_* server, as production does
SOURCE_ENV_FILE: Path | None = REPO_ROOT / '.staging.env'

# datasetDB resource types considered as "datasets" to index
RESOURCE_TYPES = ('Dataset',)
APPDB_DATASETS_TABLE = 'datasets'
DOI_BASE = 'https://doi.org/'

# Records read and committed at once, and batches read ahead while one is embedded (~3s against ~10s)
RECORD_BATCH_SIZE = 2000
PREFETCH_DEPTH = 2

# Fits the 512 token window for Latin text (~4 chars per token), embed.SAFE_CHUNK_CHARS covers the rest
MAX_CHUNK_CHARS = 1200
# Guard against pathological descriptions (full papers pasted in the metadata)
MAX_DESCRIPTION_CHUNKS = 8

# dropped for the length of a bulk load by --defer-indexes, see deferred_indexes()
DEFERRED_INDEXES = (
    'record_embeddings_diskann_idx',
    'datasets_bm25_search_text_idx',
    'datasets_bm25_title_idx',
)
# The 64MB default makes a diskann build crawl (163 min for ~1.5M vectors, against 64 min at 4GB).
INDEX_BUILD_WORK_MEM = '6GB'

# arbitrary, it only has to be stable: the appDB advisory lock a run holds, see index_datasets()
INDEXING_LOCK_KEY = 8163400227411


@dataclass
class IndexOptions:
    """Everything one indexing run needs, from the CLI or from celery task kwargs.

    Every field is JSON serializable so celery can carry it as-is.
    """

    appdb: str = 'appdb'
    limit: int | None = None
    reset: bool = False
    defer_indexes: bool = False
    # which of API_ENDPOINTS to embed with
    endpoint: str = DEFAULT_ENDPOINT
    # override that endpoint's base_url for one run, e.g. a second ferro deployment
    base_url: str | None = None
    concurrency: int | None = None
    # Per run overrides of the POSTGRES_* environment, left None in production
    source_host: str | None = None
    source_port: int | None = None
    source_db: str | None = None
    target_host: str | None = None
    target_port: int | None = None


def connection_params(
    # dotenv_values yields str | None for a bare key; os.environ's Mapping[str, str] is compatible
    env: Mapping[str, str | None],
    default_db: str,
    default_host: str,
    db: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    """Build psycopg connection params from the POSTGRES_* keys of env.

    db, host and port override env for a single run, which is what --target-host and --source-host
    pass in.
    """
    # POSTGRES_USER in the containers, POSTGRES_ADMIN in the env files a checkout has
    user, password = env.get('POSTGRES_USER') or env.get('POSTGRES_ADMIN'), env.get('POSTGRES_PASSWORD')
    if not user or not password:
        raise ValueError('Missing POSTGRES_USER (or POSTGRES_ADMIN) and POSTGRES_PASSWORD')
    return {
        'dbname': db or env.get('POSTGRES_DB') or default_db,
        'user': user,
        'password': password,
        'host': host or env.get('POSTGRES_ADDRESS') or default_host,
        'port': port or int(env.get('POSTGRES_PORT') or 5432),
    }


def source_connection_params(options: IndexOptions) -> dict[str, Any]:
    """datasetDB, read only: the harvested records this projects into appDB.

    The same server as the target unless SOURCE_ENV_FILE is set and present, see the constant.
    """
    # dotenv_values, not load_dotenv: a dict keeps these POSTGRES_* keys from overwriting the target's
    env: Mapping[str, str | None] = (
        dotenv_values(SOURCE_ENV_FILE) if SOURCE_ENV_FILE is not None and SOURCE_ENV_FILE.is_file() else os.environ
    )
    return connection_params(
        env,
        # POSTGRES_DB is datasetdb everywhere in this stack, this is only the fallback
        default_db='datasetdb',
        default_host='postgres',
        db=options.source_db,
        host=options.source_host,
        port=options.source_port,
    )


def target_connection_params(options: IndexOptions) -> dict[str, Any]:
    """appDB, written to: the hybrid search tables the SEARCH API reads."""
    return connection_params(
        os.environ,
        default_db=options.appdb,
        # the compose service name, so this works in the containers with nothing set
        default_host='postgres',
        db=options.appdb,
        host=options.target_host,
        port=options.target_port,
    )


# ============================ Objects ============================


@dataclass(slots=True)
class DataciteJson:
    """The subset of datasetdb.records.datacite_json the search API needs.

    Every field is a list of loosely typed objects (see src/utils/normalize_datacite_json.py), so
    the raw entries are left to the accessors below.
    """

    titles: list[dict[str, Any]] = field(default_factory=list)
    descriptions: list[dict[str, Any]] = field(default_factory=list)
    subjects: list[dict[str, Any]] = field(default_factory=list)
    creators: list[dict[str, Any]] = field(default_factory=list)
    dates: list[dict[str, Any]] = field(default_factory=list)
    rights_list: list[dict[str, Any]] = field(default_factory=list)
    alternate_identifiers: list[dict[str, Any]] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    publication_year: int | None = None
    doi: str | None = None
    url: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any] | None) -> 'DataciteJson':
        raw = raw or {}

        def entries(key: str) -> list[dict[str, Any]]:
            value = raw.get(key)
            return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []

        return cls(
            titles=entries('titles'),
            descriptions=entries('descriptions'),
            subjects=entries('subjects'),
            creators=entries('creators'),
            dates=entries('dates'),
            rights_list=entries('rightsList'),
            alternate_identifiers=entries('alternateIdentifiers'),
            formats=[f for f in raw.get('formats') or [] if isinstance(f, str)],
            publication_year=to_year(raw.get('publicationYear')),
            doi=raw.get('doi') if isinstance(raw.get('doi'), str) else None,
            url=raw.get('url') if isinstance(raw.get('url'), str) else None,
        )


class UnindexableRecordError(ValueError):
    """A record that cannot be turned into a datasets row, with the reason why."""


@dataclass(slots=True)
class SourceRecord:
    """One row of datasetdb.records, joined with the repository it was harvested from."""

    source_record_id: str
    doi: str | None
    url: str | None
    title: str | None
    resource_type: str
    datacite_json: dict[str, Any] | None
    datestamp: datetime
    updated_at: datetime
    repository_code: str
    repository_name: str

    @property
    def datacite(self) -> DataciteJson:
        return DataciteJson.from_json(self.datacite_json)

    @property
    def label(self) -> str:
        """How a record is identified in the logs, so a failure can be investigated by hand."""
        return f'{self.repository_code} {self.doi or self.url or "no doi/url"} [{self.source_record_id}]'


@dataclass(slots=True)
class DatasetRow:
    """A row of the appdb datasets table. Field names match the upsert's named parameters."""

    url: str
    doi: str | None
    title: str
    alt_titles: list[str]
    description: str | None
    keywords: list[str]
    creators: list[str]
    creator_identifiers: list[str]
    alternate_identifiers: list[str]
    resource_type: str
    publication_year: int | None
    publication_date: date | None
    languages: list[str]
    formats: list[str]
    license: str | None
    license_url: str | None
    repository_code: str
    repository_name: str
    search_text: str
    source_record_id: str
    source_datestamp: datetime
    source_updated_at: datetime
    # every description, abstract first, for the embeddings to cover. Not a column of the table
    descriptions_text: str = ''

    # fields of this dataclass that are not columns of the datasets table
    NON_COLUMN_FIELDS = ('descriptions_text',)

    def as_params(self) -> dict[str, Any]:
        return {column: getattr(self, column) for column in DATASET_COLUMNS}


# the datasets columns, derived from DatasetRow so the row and the upsert parameters cannot drift
DATASET_COLUMNS = tuple(f.name for f in fields(DatasetRow) if f.name not in DatasetRow.NON_COLUMN_FIELDS)


@dataclass(slots=True)
class Chunk:
    """A piece of text to embed, belonging to one named embedding of one record."""

    record_url: str
    field_name: str
    chunk_index: int
    text: str


@dataclass(slots=True)
class EmbeddedChunk:
    """A chunk with its embedding, ready to be copied into record_embeddings."""

    chunk: Chunk
    vector: list[float]

    def as_row(self) -> tuple[Any, ...]:
        return (
            self.chunk.record_url,
            self.chunk.field_name,
            self.chunk.chunk_index,
            self.chunk.text,
            # the vector input function parses the '[1,2,3]' text form, so no adapter is needed
            json.dumps(self.vector),
            EMBEDDING_MODEL.name,
        )


@dataclass(slots=True)
class IndexedCounts:
    """Progress of an indexing run."""

    datasets: int = 0
    skipped: int = 0
    failed: int = 0
    chunks: int = 0
    # Per stage timings: embed and db overlap, fetch and build block the main thread
    embed_seconds: float = 0.0
    db_seconds: float = 0.0
    fetch_seconds: float = 0.0
    build_seconds: float = 0.0

    def add(self, other: 'IndexedCounts') -> None:
        """Accumulate another set of counts into this one, field by field."""
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))


# ============================ 1. Select what needs indexing ============================


def table_exists(conn: psycopg.Connection[Any], table: str) -> bool:
    """Whether a table exists in the public schema. A fresh appDB has none of them yet."""
    with conn.cursor() as cur:
        cur.execute('SELECT to_regclass(%s)', (f'public.{table}',))
        row = cur.fetchone()
    return bool(row and row[0] is not None)


def get_indexed_state(appdb_conn: psycopg.Connection[Any]) -> dict[str, datetime]:
    """The source record ids already in appDB, with the source updated_at they were built from.

    Held in memory since the two DBs are on different servers and the diff cannot be a join.
    """
    if not table_exists(appdb_conn, APPDB_DATASETS_TABLE):
        logger.info(f'appDB table "{APPDB_DATASETS_TABLE}" does not exist yet, all datasets need indexing')
        return {}
    query = sql.SQL('SELECT source_record_id, source_updated_at FROM {}').format(sql.Identifier(APPDB_DATASETS_TABLE))
    # server side cursor: a client side one downloads the whole table before the dict is built
    with appdb_conn.cursor(name='indexed_state') as cur:
        cur.itersize = 50000
        cur.execute(query)
        return dict(cur)


# Projected in SQL to leave '_additional_metadata' behind, ~90% of the document: 27s per 2000 records against 5s
DATACITE_KEYS = (
    'titles',
    'descriptions',
    'subjects',
    'creators',
    'dates',
    'rightsList',
    'alternateIdentifiers',
    'formats',
    'publicationYear',
    'doi',
    'url',
)

# Shared by the indexing query and --count. Never ORDER BY: sorting the JSON cost ~9 min on 400k records
RECORDS_SOURCE = """
    FROM records rec
    JOIN repositories repo ON rec.repository_id = repo.id
    WHERE rec.resource_type = ANY(%(resource_types)s)
      AND rec.datacite_json IS NOT NULL
"""

# interpolates DATACITE_KEYS, a module constant, not user input
SELECT_RECORDS_QUERY = f"""
    SELECT
        rec.id AS source_record_id,
        rec.doi,
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
    {RECORDS_SOURCE}
"""

COUNT_RECORDS_QUERY = f'SELECT rec.id, rec.updated_at, repo.code {RECORDS_SOURCE}'


def iter_records_to_index(
    datasetdb_conn: psycopg.Connection[Any],
    indexed: dict[str, datetime],
    limit: int | None = None,
) -> Iterator[list[SourceRecord]]:
    """Stream the datasetDB records that need (re)indexing, in batches.

    Server side cursor: the source table holds hundreds of thousands of rows with their JSON.
    """
    yielded = 0
    batch: list[SourceRecord] = []
    with datasetdb_conn.cursor(name='records_to_index', row_factory=class_row(SourceRecord)) as cur:
        cur.itersize = RECORD_BATCH_SIZE
        cur.execute(SELECT_RECORDS_QUERY, {'resource_types': list(RESOURCE_TYPES)})
        for record in cur:
            if not needs_indexing(record.source_record_id, record.updated_at, indexed):
                continue
            batch.append(record)
            yielded += 1
            if len(batch) >= RECORD_BATCH_SIZE or (limit and yielded >= limit):
                yield batch
                batch = []
            if limit and yielded >= limit:
                return
    if batch:
        yield batch


def prefetch(batches: Iterator[list[SourceRecord]], depth: int = PREFETCH_DEPTH) -> Iterator[list[SourceRecord]]:
    """Read the next batches from datasetDB while the current one is embedded and inserted.

    Only the single pool thread touches the source cursor and futures are consumed in submission
    order, so batches stay ordered.
    """

    def read_next() -> list[SourceRecord] | None:
        """None marks the end of the source, so it can travel through a Future."""
        return next(batches, None)

    with ThreadPoolExecutor(max_workers=1) as pool:
        queued: deque[Future[list[SourceRecord] | None]] = deque(pool.submit(read_next) for _ in range(depth))
        while (batch := queued.popleft().result()) is not None:
            queued.append(pool.submit(read_next))
            yield batch


def needs_indexing(source_record_id: str, updated_at: datetime, indexed: dict[str, datetime]) -> bool:
    """Whether a datasetDB record is missing from appDB or outdated there."""
    indexed_at = indexed.get(source_record_id)
    return indexed_at is None or updated_at > indexed_at


def count_to_index(datasetdb_conn: psycopg.Connection[Any], indexed: dict[str, datetime]) -> tuple[int, dict[str, int]]:
    """Count the records left to index, in total and per repository."""
    total = 0
    per_repo: dict[str, int] = {}
    with datasetdb_conn.cursor(name='count_to_index') as cur:
        cur.itersize = 10000
        cur.execute(COUNT_RECORDS_QUERY, {'resource_types': list(RESOURCE_TYPES)})
        for record_id, updated_at, repository_code in cur:
            if needs_indexing(record_id, updated_at, indexed):
                total += 1
                per_repo[repository_code] = per_repo.get(repository_code, 0) + 1
    return total, dict(sorted(per_repo.items(), key=lambda kv: -kv[1]))


# ============================ 2. Build the appDB row ============================


def normalize_doi(doi: str | None) -> str | None:
    """Reduce a DOI to its bare id: the source stores either '10.x/y' or a resolver URL."""
    if not doi:
        return None
    doi = doi.strip()
    if doi.lower().startswith('doi:'):
        doi = doi[4:]
    if doi.lower().startswith('http'):
        # any resolver prefix (doi.org, dx.doi.org, ...): the DOI starts at the '10.' prefix
        start = doi.find('10.')
        if start == -1:
            return None
        doi = doi[start:]
    return doi or None


def dataset_url(doi: str | None, url: str | None) -> str | None:
    """Primary key of a dataset in appDB: the DOI resolver URL, or the landing page URL."""
    bare_doi = normalize_doi(doi)
    if bare_doi:
        return DOI_BASE + bare_doi
    return url.strip() if url else None


def subfield_values(entries: list[dict[str, Any]], subfield: str) -> list[str]:
    """Collect the non empty values of a subfield in a DataCite JSON list of objects."""
    values = []
    for entry in entries:
        if isinstance(value := entry.get(subfield), str) and value.strip():
            values.append(' '.join(value.split()))
    return values


def first(values: list[str]) -> str | None:
    """First value of a list, or None when empty."""
    return values[0] if values else None


def unique(values: list[str]) -> list[str]:
    """Deduplicate while keeping the original order."""
    return list(dict.fromkeys(values))


def to_year(value: Any) -> int | None:
    match = re.search(r'\d{4}', str(value)) if value is not None else None
    return int(match.group()) if match else None


def sort_descriptions(descriptions: list[dict[str, Any]]) -> list[str]:
    """All the descriptions of a record, abstracts first, longest first within a type.

    A record often carries several complementary descriptions (Abstract, Methods, TechnicalInfo,
    ...), none redundant: the caller uses the first for display and the whole list for search.
    """
    entries = [
        (entry.get('descriptionType') or 'Other', ' '.join(entry['description'].split()))
        for entry in descriptions
        if isinstance(entry.get('description'), str) and entry['description'].strip()
    ]
    entries.sort(key=lambda e: (e[0] != 'Abstract', -len(e[1])))
    # the descriptionType only serves to order them here, it is not stored anywhere
    return unique([text for _, text in entries])


def pick_titles(titles: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    """Primary title plus the alternative ones."""
    primary, alt = None, []
    for entry in titles:
        if not isinstance(value := entry.get('title'), str) or not value.strip():
            continue
        value = ' '.join(value.split())
        if primary is None and not entry.get('titleType'):
            primary = value
        else:
            alt.append(value)
    if primary is None and alt:
        # only alternative titles: promote the first, so the row always has a title
        primary, alt = alt[0], alt[1:]
    # records do repeat their main title as an alternative one, keep it in one place only
    return primary, [title for title in unique(alt) if title != primary]


def pick_publication_date(dates: list[dict[str, Any]], publication_year: int | None) -> date | None:
    """Best available publication date, falling back to the first day of the publication year."""
    by_type: dict[str, str] = {}
    for entry in dates:
        if isinstance(entry.get('date'), str):
            by_type.setdefault(entry.get('dateType') or 'Other', entry['date'])
    for date_type in ('Issued', 'Available', 'Created', 'Submitted', 'Updated', 'Other'):
        if value := by_type.get(date_type):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                continue
    return date(publication_year, 1, 1) if publication_year else None


def pick_languages(datacite: DataciteJson) -> list[str]:
    """Languages declared on the titles, descriptions and subjects."""
    langs = []
    for entries in (datacite.titles, datacite.descriptions, datacite.subjects):
        langs.extend(subfield_values(entries, 'lang'))
    return unique([lang.lower()[:8] for lang in langs])


def build_dataset_row(record: SourceRecord) -> DatasetRow:
    """Build the appDB datasets row from a datasetDB record.

    Raises UnindexableRecordError when it has no URL/DOI for the primary key, or no title.
    """
    datacite = record.datacite
    url = dataset_url(record.doi or datacite.doi, record.url or datacite.url)
    if not url:
        raise UnindexableRecordError('no URL and no DOI to build one from')

    title, alt_titles = pick_titles(datacite.titles)
    title = title or (record.title and ' '.join(record.title.split()))
    if not title:
        raise UnindexableRecordError('no title in datacite_json nor on the record')

    keywords = unique(subfield_values(datacite.subjects, 'subject'))
    creators = unique(subfield_values(datacite.creators, 'creatorName'))
    creator_identifiers = unique(
        [
            value
            for creator in datacite.creators
            for value in subfield_values(
                [n for n in creator.get('nameIdentifiers') or [] if isinstance(n, dict)], 'nameIdentifier'
            )
        ]
    )
    # some repositories (HAL) have no publicationYear at all, but do have dates
    publication_date = pick_publication_date(datacite.dates, datacite.publication_year)

    # Everything a keyword search should be able to match, in one BM25 haystack
    descriptions = sort_descriptions(datacite.descriptions)
    search_text = '\n'.join([title, *alt_titles, *descriptions, ' '.join(keywords), ' '.join(creators)]).strip()

    return DatasetRow(
        url=url[:2048],
        doi=normalize_doi(record.doi or datacite.doi),
        title=title,
        alt_titles=alt_titles,
        description=first(descriptions),
        keywords=keywords,
        creators=creators,
        creator_identifiers=creator_identifiers,
        alternate_identifiers=unique(subfield_values(datacite.alternate_identifiers, 'alternateIdentifier')),
        resource_type=record.resource_type,
        publication_year=datacite.publication_year or (publication_date.year if publication_date else None),
        publication_date=publication_date,
        languages=pick_languages(datacite),
        formats=unique(datacite.formats),
        license=first(subfield_values(datacite.rights_list, 'rights')),
        license_url=first(subfield_values(datacite.rights_list, 'rightsURI')),
        repository_code=record.repository_code,
        repository_name=record.repository_name,
        search_text=search_text,
        source_record_id=record.source_record_id,
        source_datestamp=record.datestamp,
        source_updated_at=record.updated_at,
        descriptions_text='\n\n'.join(descriptions),
    )


# ============================ 3. Chunk the text to embed ============================


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS, max_chunks: int = MAX_DESCRIPTION_CHUNKS) -> list[str]:
    """Split a long text into chunks of at most max_chars, on word boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ''
    for word in text.split(' '):
        if current and len(current) + 1 + len(word) > max_chars:
            chunks.append(current)
            if len(chunks) >= max_chunks:
                return chunks
            current = word
        else:
            current = f'{current} {word}' if current else word
    if current and len(chunks) < max_chunks:
        chunks.append(current)
    return chunks


def dataset_chunks(row: DatasetRow) -> list[Chunk]:
    """Named chunks to embed for a dataset: one named embedding per field, split when too long.

    Every field needs the split, some records have a paragraph as a title or hundreds of subjects.

    TODO: the DataCite descriptionType of each chunk is lost here, so the search API cannot tell an
    abstract chunk from a methods one. If that matters for snippets or weighting, add a
    `chunk_type` column and carry the type from sort_descriptions() down to the Chunk.
    """
    chunks: list[Chunk] = []
    # a truncated title or keyword list stays representative, a description loses real content
    for field_name, text, max_chunks in (
        ('title', row.title, 1),
        ('keywords', ', '.join(row.keywords), 2),
        ('description', row.descriptions_text, MAX_DESCRIPTION_CHUNKS),
    ):
        if not text or not text.strip():
            continue
        chunks.extend(
            Chunk(row.url, field_name, i, chunk) for i, chunk in enumerate(split_text(text, max_chunks=max_chunks))
        )
    return chunks


# Built from DATASET_COLUMNS, so a new DatasetRow field is enough. cast: psycopg wants a LiteralString
UPSERT_DATASET_SQL = cast(  # type: ignore[redundant-cast]
    'LiteralString',
    f"""
    INSERT INTO datasets ({', '.join(DATASET_COLUMNS)}, indexed_at)
    VALUES ({', '.join(f'%({column})s' for column in DATASET_COLUMNS)}, now())
    ON CONFLICT (url) DO UPDATE SET
        {', '.join(f'{column} = EXCLUDED.{column}' for column in DATASET_COLUMNS if column != 'url')},
        indexed_at = now()
""",  # noqa: S608
)

COPY_EMBEDDINGS_SQL = """
    COPY record_embeddings (record_url, field, chunk_index, chunk_text, embedding, model)
    FROM STDIN
"""


def upsert_datasets(appdb_conn: psycopg.Connection[Any], rows: list[DatasetRow], embedded: list[EmbeddedChunk]) -> None:
    """Write a batch of datasets and their embeddings in a single transaction."""
    with appdb_conn.cursor() as cur:
        cur.executemany(UPSERT_DATASET_SQL, [row.as_params() for row in rows])
        # replaced, not merged: a re-index can produce a different number of chunks per dataset
        cur.execute('DELETE FROM record_embeddings WHERE record_url = ANY(%s)', ([row.url for row in rows],))
        # COPY rather than executemany, a batch carries thousands of 768 float vectors
        with cur.copy(COPY_EMBEDDINGS_SQL) as copy:
            for item in embedded:
                copy.write_row(item.as_row())
    appdb_conn.commit()


@contextmanager
def deferred_indexes(
    appdb_conn: psycopg.Connection[Any], *, enabled: bool, index_names: tuple[str, ...] = DEFERRED_INDEXES
) -> Iterator[None]:
    """Drop the search indexes for the duration of a bulk load, and recreate them at the end.

    Worth it for the initial load of the whole warehouse, not for an incremental run: rebuilding a
    360MB diskann graph for a few hundred rows is slower than inserting into it.

    No DDL is duplicated: creating the indexes belongs to create_sql/appdb/indexes.sql, and what
    goes back up is what postgres itself handed over in pg_indexes.indexdef. Those definitions only
    live in this process, so a SIGKILL loses them and that file has to be run again.
    """
    if not enabled:
        yield
        return

    with appdb_conn.cursor() as cur:
        cur.execute(
            'SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s AND indexname = ANY(%s)',
            ('public', list(index_names)),
        )
        dropped: dict[str, str] = dict(cur.fetchall())
        for name in dropped:
            cur.execute(sql.SQL('DROP INDEX {}').format(sql.Identifier(name)))
    appdb_conn.commit()
    logger.info(f'dropped {len(dropped)} search indexes for the bulk load: {", ".join(dropped) or "none"}')

    try:
        yield
    finally:
        if dropped:
            # the SET has to share this connection or it would not apply to the build
            logger.info(f'rebuilding {len(dropped)} search indexes (maintenance_work_mem {INDEX_BUILD_WORK_MEM})')
            with appdb_conn.cursor() as cur:
                cur.execute(f"SET maintenance_work_mem = '{INDEX_BUILD_WORK_MEM}'")
                cur.execute('SET max_parallel_maintenance_workers = 4')
                for name, definition in dropped.items():
                    started = time.monotonic()
                    # postgres' own reconstruction of the statement, trusted but not a literal
                    cur.execute(cast('LiteralString', definition))  # type: ignore[redundant-cast]
                    logger.info(f'  {name} built in {human_duration(time.monotonic() - started)}')
            appdb_conn.commit()


def verify_stored_embeddings(appdb_conn: psycopg.Connection[Any], embedder: ApiEmbeddings, sample_size: int) -> int:
    """Check that stored vectors actually match their chunk_text, on a random sample.

    Sampled by md5(record_url), not in heap order: the rows inserted first are the correct ones,
    so a spot check of the first rows looks fine while the rest of the table is broken.
    """
    with appdb_conn.cursor() as cur:
        cur.execute(
            """
            SELECT record_url, field, chunk_index, chunk_text, embedding::text
            FROM record_embeddings
            ORDER BY md5(record_url)
            LIMIT %s
            """,
            (sample_size,),
        )
        rows = cur.fetchall()

    if not rows:
        logger.info('no embeddings stored, nothing to verify')
        return 0

    logger.info(f'verifying {len(rows)} random chunks against a batch of 1 re-embedding of their text')
    similarities = []
    mismatches = 0
    for record_url, field_name, chunk_index, chunk_text, stored_text in rows:
        stored = json.loads(stored_text)
        fresh = embedder.embed_batch([chunk_text])[0]
        similarity = cosine_similarity(stored, fresh)
        similarities.append(similarity)
        if similarity < VERIFY_MIN_COSINE:
            mismatches += 1
            logger.error(f'mismatch {similarity:.4f} {record_url} {field_name}[{chunk_index}]')

    matched = len(rows) - mismatches
    logger.info(
        f'{matched}/{len(rows)} match ({matched / len(rows):.1%}), '
        f'mean similarity {sum(similarities) / len(similarities):.4f}, worst {min(similarities):.4f}'
    )
    if mismatches:
        logger.error(f'{mismatches} stored vectors do not match their text, the embeddings need to be rebuilt')
    return mismatches


def check_batching(datasetdb_conn: psycopg.Connection[Any], options: IndexOptions, size: int) -> float:
    """Check an endpoint answers a batch the way it answers the same texts one at a time.

    On real chunks, since the question is load and length dependent: an endpoint that disagrees
    with itself here is degrading every search built on its vectors, and its batch_size has to come
    down. Only ever run on request, see --check-batching.
    """
    records = next(iter_records_to_index(datasetdb_conn, {}, limit=size), [])
    _, chunks = build_batch(records)
    texts = list(dict.fromkeys(chunk.text for chunk in chunks))[:size]
    if not texts:
        logger.error('no chunks to check, is the source empty?')
        return 0.0
    with embedder_for(options) as embedder:
        logger.info(embedder.describe())
        worst = embedder.check_batching(texts, sample=len(texts))
    if worst < VERIFY_MIN_COSINE:
        logger.error(f'worst similarity {worst:.6f} is below {VERIFY_MIN_COSINE}, lower this batch_size')
    return worst


def reset_datasets(appdb_conn: psycopg.Connection[Any]) -> None:
    """Empty the datasets table, so the next run reindexes from scratch.

    TRUNCATE CASCADE takes record_embeddings with it, through the foreign key.
    """
    if not table_exists(appdb_conn, APPDB_DATASETS_TABLE):
        logger.info(f'appDB table "{APPDB_DATASETS_TABLE}" does not exist yet, nothing to reset')
        return
    with appdb_conn.cursor() as cur:
        cur.execute(sql.SQL('TRUNCATE {} CASCADE').format(sql.Identifier(APPDB_DATASETS_TABLE)))
    appdb_conn.commit()
    logger.info(f'reset: deleted every row of {APPDB_DATASETS_TABLE} and record_embeddings')


# ============================ Run the pipeline ============================


def build_batch(records: list[SourceRecord]) -> tuple[list[DatasetRow], list[Chunk]]:
    """Turn a batch of source records into appDB rows and the chunks to embed for them.

    Records that do not make it are reported on stderr with their DOI or URL: one bad record never
    aborts a run.
    """
    rows: list[DatasetRow] = []
    chunks: list[Chunk] = []
    seen_urls: set[str] = set()
    for record in records:
        try:
            row = build_dataset_row(record)
        except UnindexableRecordError as e:
            logger.warning(f'skipped {record.label}: {e}')
            continue
        except Exception as e:  # never let one malformed record kill the run
            logger.warning(f'skipped {record.label}: {type(e).__name__}: {e}')
            continue

        if row.url in seen_urls:
            # the executemany upsert cannot update a row it inserted in the same statement
            logger.warning(f'skipped {record.label}: duplicate of {row.url} earlier in the same batch')
            continue

        seen_urls.add(row.url)
        rows.append(row)
        chunks.extend(dataset_chunks(row))
    return rows, chunks


def embed_chunks(embedder: ApiEmbeddings, chunks: list[Chunk]) -> list[EmbeddedChunk]:
    """Pair every chunk with its vector, ready to be copied into record_embeddings."""
    vectors = embedder.embed_texts([chunk.text for chunk in chunks])
    return [EmbeddedChunk(chunk, vector) for chunk, vector in zip(chunks, vectors, strict=True)]


def index_records(
    appdb_conn: psycopg.Connection[Any],
    embedder: ApiEmbeddings,
    batches: Iterator[list[SourceRecord]],
    on_batch: Callable[[IndexedCounts, IndexedCounts], None] | None = None,
) -> IndexedCounts:
    """Index a stream of record batches, as a 3 stage pipeline.

    While a batch is embedded, the previous one is written to appDB and the next read from
    datasetDB: the write is ~20% of a batch and the read ~50%, so overlapping them hides almost
    everything that is not embedding.

    Only the single pool thread touches appdb_conn and the previous write is awaited before the
    next is submitted, so batches land in order and errors surface immediately.
    """
    totals = IndexedCounts()
    with ThreadPoolExecutor(max_workers=1) as db_pool:
        pending: Future[WriteResult] | None = None
        while True:
            # blocking here is the part of the source fetch the prefetch could not hide
            fetch_started = time.monotonic()
            records = next(batches, None)
            fetch_seconds = time.monotonic() - fetch_started
            if records is None:
                break

            build_started = time.monotonic()
            rows, chunks = build_batch(records)
            build_seconds = time.monotonic() - build_started
            if not rows:
                totals.add(
                    IndexedCounts(skipped=len(records), fetch_seconds=fetch_seconds, build_seconds=build_seconds)
                )
                continue

            embed_started = time.monotonic()
            embedded = embed_chunks(embedder, chunks)
            counts = IndexedCounts(
                datasets=len(rows),
                skipped=len(records) - len(rows),
                chunks=len(chunks),
                embed_seconds=time.monotonic() - embed_started,
                fetch_seconds=fetch_seconds,
                build_seconds=build_seconds,
            )

            if pending is not None:
                counts.add(write_counts(pending))
            pending = db_pool.submit(timed_upsert, appdb_conn, rows, embedded)

            totals.add(counts)
            if on_batch:
                on_batch(counts, totals)
        if pending is not None:
            totals.add(write_counts(pending))
    return totals


@dataclass(slots=True)
class WriteResult:
    """Outcome of writing one batch to appDB."""

    seconds: float
    failed: int = 0


def write_counts(pending: Future[WriteResult]) -> IndexedCounts:
    """Wait for a batch write and turn its outcome into counts to accumulate.

    Its rows were already counted as indexed one batch earlier, when they were embedded, so the
    ones that failed to write have to be counted back out here.
    """
    written = pending.result()
    return IndexedCounts(datasets=-written.failed, failed=written.failed, db_seconds=written.seconds)


def timed_upsert(
    appdb_conn: psycopg.Connection[Any], rows: list[DatasetRow], embedded: list[EmbeddedChunk]
) -> WriteResult:
    """upsert_datasets, timed, and falling back to row by row on failure.

    A batch write is one transaction, so a single bad row takes it all down without saying which
    one. The retry names the offenders on stderr and still lands the rest of the batch.
    """
    started = time.monotonic()
    try:
        upsert_datasets(appdb_conn, rows, embedded)
        return WriteResult(time.monotonic() - started)
    except psycopg.Error as e:
        appdb_conn.rollback()
        logger.warning(f'batch write of {len(rows)} datasets failed ({e}), retrying row by row')

    by_url: dict[str, list[EmbeddedChunk]] = {}
    for item in embedded:
        by_url.setdefault(item.chunk.record_url, []).append(item)

    failed = 0
    for row in rows:
        try:
            upsert_datasets(appdb_conn, [row], by_url.get(row.url, []))
        except psycopg.Error as e:
            appdb_conn.rollback()
            failed += 1
            reason = str(e).strip().splitlines()[0]
            logger.error(f'failed {row.repository_code} {row.doi or row.url}: {reason}')
    return WriteResult(time.monotonic() - started, failed)


def human_duration(seconds: float) -> str:
    """A duration to read at a glance: 45s, 3m20s, 1h04m."""
    if seconds < 60:
        return f'{seconds:.0f}s'
    if seconds < 3600:
        return f'{int(seconds // 60)}m{int(seconds % 60):02d}s'
    return f'{int(seconds // 3600)}h{int(seconds % 3600 // 60):02d}m'


def exit_on_signal(signum: int, _frame: Any) -> None:
    """Turn a termination signal into an exception, so the index rebuild in the finally still runs.

    For SIGTERM and SIGHUP (a closed terminal, which once left appDB with no search indexes at
    all); SIGINT already raises KeyboardInterrupt and SIGKILL cannot be caught.
    """
    raise SystemExit(f'terminated by signal {signum}')


def embedder_for(options: IndexOptions) -> ApiEmbeddings:
    """The embeddings client the endpoint options of a run select."""
    return build_embedder(
        options.endpoint,
        base_url=options.base_url,
        concurrency=options.concurrency,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--appdb', default='appdb', help='target DB name in the local postgres')
    parser.add_argument('--limit', type=int, help='max number of datasets to index in this run')
    parser.add_argument('--count', action='store_true', help='only count what is left to index, per repository')
    parser.add_argument(
        '--reset', action='store_true', help='delete every indexed dataset and its embeddings before indexing'
    )
    parser.add_argument(
        '--defer-indexes',
        action='store_true',
        help='drop the BM25 and vector indexes during the run and rebuild them at the end '
        '(implied by --reset, since a full re-index is a bulk load)',
    )
    parser.add_argument(
        '--verify',
        type=int,
        metavar='N',
        help='check that N random stored embeddings still match their chunk_text, then exit',
    )
    parser.add_argument(
        '--check-batching',
        type=int,
        metavar='N',
        help='check the endpoint returns the same vectors for a batch of N real chunks as for those '
        'chunks embedded one at a time, then exit. Run it before trusting a new endpoint or a '
        'raised batch_size, nothing is verified during a normal run',
    )
    parser.add_argument(
        '--endpoint',
        choices=list(API_ENDPOINTS),
        default=DEFAULT_ENDPOINT,
        help='which embeddings API to use (default %(default)s: ours, no key and no rate limit). '
        + '; '.join(
            f'{key}: {ep.name}, batches of {ep.batch_size} x {ep.concurrency} parallel'
            + (f', needs {ep.api_key_env}' if ep.api_key_env else '')
            + (', every batch verified' if ep.verify_every_batch else '')
            for key, ep in API_ENDPOINTS.items()
        ),
    )
    parser.add_argument(
        '--base-url',
        help="override the selected endpoint's base URL for this run, e.g. a second ferro deployment",
    )
    parser.add_argument(
        '--concurrency',
        type=int,
        help="override the selected endpoint's parallel request count, see --endpoint for the defaults",
    )
    parser.add_argument(
        '--source-host',
        help='datasetDB host to read the harvested records from, overriding both POSTGRES_ADDRESS and SOURCE_ENV_FILE',
    )
    parser.add_argument('--source-port', type=int, help='datasetDB port, same override')
    parser.add_argument('--source-db', help='datasetDB name, same override (default datasetdb)')
    parser.add_argument(
        '--target-host',
        help='appDB host, overriding POSTGRES_ADDRESS. Use 127.0.0.1 to write the local postgres '
        'from a checkout, the default "postgres" is the compose service name',
    )
    parser.add_argument('--target-port', type=int, help='appDB port, overriding POSTGRES_PORT')
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='log per batch timings, and a line for every batch the verification splits',
    )
    args = parser.parse_args()

    # only present in a checkout, so a dev run needs no exported variables
    for env_file in DEV_ENV_FILES:
        if env_file.is_file():
            load_dotenv(env_file)
    signal.signal(signal.SIGTERM, exit_on_signal)
    signal.signal(signal.SIGHUP, exit_on_signal)
    # only the CLI configures logging: celery and airflow bring their own handlers and capture ours
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-7s %(message)s', datefmt='%H:%M:%S')
    if args.verbose:
        # this package only: DEBUG on the root logger is one urllib3 line per embeddings request
        logging.getLogger(__name__.rsplit('.', 1)[0]).setLevel(logging.DEBUG)

    options = IndexOptions(**{field.name: getattr(args, field.name) for field in fields(IndexOptions)})

    if args.verify is not None or args.check_batching is not None or args.count:
        with connections(options) as (appdb_conn, datasetdb_conn):
            if args.verify is not None:
                with embedder_for(options) as embedder:
                    mismatches = verify_stored_embeddings(appdb_conn, embedder, args.verify)
                sys.exit(1 if mismatches else 0)
            elif args.check_batching is not None:
                worst = check_batching(datasetdb_conn, options, args.check_batching)
                sys.exit(1 if worst < VERIFY_MIN_COSINE else 0)
            else:
                indexed = get_indexed_state(appdb_conn)
                total, per_repo = count_to_index(datasetdb_conn, indexed)
                logger.info(f'{total} datasets to index (already indexed in appDB: {len(indexed)})')
                for code, count in per_repo.items():
                    logger.info(f'  {code}: {count}')
        return

    index_datasets(options)


@contextmanager
def connections(options: IndexOptions) -> Iterator[tuple[psycopg.Connection[Any], psycopg.Connection[Any]]]:
    """Open appDB (written to) and datasetDB (read only), reporting which servers they landed on."""
    source_params = source_connection_params(options)
    target_params = target_connection_params(options)
    source = f'{source_params["host"]}:{source_params["port"]}/{source_params["dbname"]}'
    target = f'{target_params["host"]}:{target_params["port"]}/{target_params["dbname"]}'
    logger.info(f'indexing datasetDB {source} into appDB {target}')
    with psycopg.connect(**target_params) as appdb_conn, psycopg.connect(**source_params) as datasetdb_conn:
        yield appdb_conn, datasetdb_conn


def index_datasets(options: IndexOptions) -> IndexedCounts:
    """Project datasetDB records into appDB. The entry point for both the CLI and the celery task.

    Only one run may write appDB at a time: two would fetch the same records, embed them twice and
    race on the same rows. A session level advisory lock is the guard, and postgres releases it when
    the connection goes, including on a crash.
    """
    with connections(options) as (appdb_conn, datasetdb_conn):
        with appdb_conn.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(%s)', (INDEXING_LOCK_KEY,))
            row = cur.fetchone()
            if not row or not row[0]:
                raise RuntimeError('another indexing run holds the appDB lock, not starting a second one')

        if options.reset:
            reset_datasets(appdb_conn)
        indexed = get_indexed_state(appdb_conn)
        return run_indexing(options, appdb_conn, datasetdb_conn, indexed)


def run_indexing(
    options: IndexOptions,
    appdb_conn: psycopg.Connection[Any],
    datasetdb_conn: psycopg.Connection[Any],
    indexed: dict[str, datetime],
) -> IndexedCounts:
    """Index everything that needs it, one INFO line of progress per batch."""
    # a few seconds of scanning, worth it to know where the run stands and to give it an eta
    to_index, _ = count_to_index(datasetdb_conn, indexed)
    target = min(options.limit, to_index) if options.limit else to_index
    batches = max(-(-target // RECORD_BATCH_SIZE), 1)
    logger.info(f'{to_index} datasets to index, {len(indexed)} already in appDB')
    logger.info(f'this run: {target} datasets in {batches} batches of up to {RECORD_BATCH_SIZE}')
    started = time.monotonic()
    with embedder_for(options) as embedder:
        logger.info(embedder.describe())
        done = 0

        def report(batch: IndexedCounts, totals: IndexedCounts) -> None:
            """Where the run is, how fast it is going, and when it should end."""
            nonlocal done
            done += 1
            elapsed = time.monotonic() - started
            seen = totals.datasets + totals.skipped + totals.failed
            rate = totals.datasets / elapsed
            issues = f' | {totals.skipped} skipped, {totals.failed} failed' if totals.skipped or totals.failed else ''
            eta = f'eta {human_duration((target - seen) / rate)}' if rate and seen < target else 'last batch'
            logger.info(
                f'batch {done}/{batches} | {seen}/{target} datasets {seen / target:.0%} | '
                f'{totals.chunks} chunks | {rate:.0f} datasets/s{issues} | {eta}'
            )
            # the stage timings only matter when tuning, and embedder.stats() every batch is noise
            logger.debug(
                f'  fetch {batch.fetch_seconds:.1f}s build {batch.build_seconds:.1f}s '
                f'embed {batch.embed_seconds:.1f}s db {batch.db_seconds:.1f}s | {embedder.stats()}'
            )

        # a full re-index is a bulk load too, and filling the diskann graph by insert wrecks it
        with deferred_indexes(appdb_conn, enabled=options.defer_indexes or options.reset):
            counts = index_records(
                appdb_conn,
                embedder,
                prefetch(iter_records_to_index(datasetdb_conn, indexed, limit=options.limit)),
                on_batch=report,
            )

        elapsed = time.monotonic() - started
        logger.info(
            f'done: {counts.datasets} datasets indexed, {counts.chunks} chunks, '
            f'{counts.skipped} skipped, {counts.failed} failed, in {human_duration(elapsed)}'
        )
        if counts.datasets:
            logger.info(
                f'{counts.datasets / elapsed:.0f} datasets/s, {counts.chunks / elapsed:.0f} chunks/s, '
                f'{counts.chunks / counts.datasets:.2f} chunks per dataset | '
                f'embedding {counts.embed_seconds / elapsed:.0%} of the run, '
                f'appDB writes {counts.db_seconds / elapsed:.0%} (overlapping)'
            )
            logger.info(f'embeddings: {embedder.stats()}')
    return counts


if __name__ == '__main__':
    main()
