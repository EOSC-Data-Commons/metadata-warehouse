import json
import logging
import re
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from typing import Any

from src.utils import embedding_utils

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
    'url',
)

RESOURCE_TYPES = ('Dataset',)

# Fits the 512 token window for Latin text (~4 chars per token), embed.SAFE_CHUNK_CHARS covers the rest
MAX_CHUNK_CHARS = 1200
# Guard against pathological descriptions (full papers pasted in the metadata)
MAX_DESCRIPTION_CHUNKS = 8


class UnindexableRecordError(ValueError):
    """A record that cannot be turned into a datasets row, with the reason why."""


@dataclass(slots=True)
class DatasetRow:
    """A row of the appdb datasets table. Field names match the upsert's named parameters."""

    url: str
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
            url=raw.get('url') if isinstance(raw.get('url'), str) else None,
        )


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
    model: str

    def as_row(self) -> tuple[Any, ...]:
        return (
            self.chunk.record_url,
            self.chunk.field_name,
            self.chunk.chunk_index,
            self.chunk.text,
            # the vector input function parses the '[1,2,3]' text form, so no adapter is needed
            json.dumps(self.vector),
            self.model,
        )


@dataclass(slots=True)
class SourceRecord:
    """One row of datasetdb.records, joined with the repository it was harvested from."""

    source_record_id: str
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
        return f'{self.repository_code} {self.url or "no doi/url"} [{self.source_record_id}]'


def subfield_values(entries: list[dict[str, Any]], subfield: str) -> list[str]:
    """Collect the non empty values of a subfield in a DataCite JSON list of objects."""
    values = []
    for entry in entries:
        if isinstance(value := entry.get(subfield), str) and value.strip():
            values.append(' '.join(value.split()))
    return values


def unique(values: list[str]) -> list[str]:
    """Deduplicate while keeping the original order."""
    return list(dict.fromkeys(values))


def to_year(value: Any) -> int | None:
    match = re.search(r'\d{4}', str(value)) if value is not None else None
    return int(match.group()) if match else None


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


def first(values: list[str]) -> str | None:
    """First value of a list, or None when empty."""
    return values[0] if values else None


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
    url = record.url or datacite.url
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


def embed_chunks(
    chunks: list[Chunk], api_key: str, embed_api: str, model: str, batch_size: int, logger: logging.Logger
) -> list[EmbeddedChunk]:
    """Pair every chunk with its vector, ready to be copied into record_embeddings."""
    vectors = embedding_utils.embed(
        [chunk.text for chunk in chunks], api_key, embed_api, logger, model, batch_size=batch_size
    )
    return [EmbeddedChunk(chunk, vector, model) for chunk, vector in zip(chunks, vectors, strict=True)]
