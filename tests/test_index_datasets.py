"""Tests for the pure transformation functions of the dataset indexing pipeline.

Everything here runs without a database or an embeddings endpoint: what is covered is the
datasetdb.records -> appdb.datasets projection, the chunking and the batch level guards.
"""

import unittest
from datetime import UTC, date, datetime

from src.transform.index_datasets import (
    MAX_CHUNK_CHARS,
    MAX_DESCRIPTION_CHUNKS,
    DataciteJson,
    SourceRecord,
    UnindexableRecordError,
    build_batch,
    build_dataset_row,
    dataset_chunks,
    dataset_url,
    needs_indexing,
    normalize_doi,
    pick_publication_date,
    pick_titles,
    sort_descriptions,
    split_text,
    subfield_values,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def record(**overrides: object) -> SourceRecord:
    """A minimal indexable record, with the field under test overridden."""
    defaults = {
        'source_record_id': 'oai:zenodo:1',
        'doi': '10.5281/zenodo.1',
        'url': None,
        'title': None,
        'resource_type': 'Dataset',
        'datacite_json': {'titles': [{'title': 'A title'}]},
        'datestamp': NOW,
        'updated_at': NOW,
        'repository_code': 'zenodo',
        'repository_name': 'Zenodo',
    }
    return SourceRecord(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestIdentifiers(unittest.TestCase):
    def test_normalize_doi_strips_every_prefix_form(self):
        for raw in (
            '10.5281/zenodo.1',
            ' 10.5281/zenodo.1 ',
            'doi:10.5281/zenodo.1',
            'https://doi.org/10.5281/zenodo.1',
            'http://dx.doi.org/10.5281/zenodo.1',
        ):
            self.assertEqual(normalize_doi(raw), '10.5281/zenodo.1', raw)

    def test_normalize_doi_rejects_a_url_that_is_not_a_doi(self):
        self.assertIsNone(normalize_doi('https://example.org/records/1'))
        self.assertIsNone(normalize_doi(''))
        self.assertIsNone(normalize_doi(None))

    def test_dataset_url_prefers_the_doi_resolver_url(self):
        self.assertEqual(
            dataset_url('10.5281/zenodo.1', 'https://zenodo.org/records/1'), 'https://doi.org/10.5281/zenodo.1'
        )

    def test_dataset_url_falls_back_to_the_landing_page(self):
        self.assertEqual(dataset_url(None, ' https://zenodo.org/records/1 '), 'https://zenodo.org/records/1')
        self.assertIsNone(dataset_url(None, None))


class TestDataciteAccessors(unittest.TestCase):
    def test_from_json_drops_entries_of_the_wrong_shape(self):
        datacite = DataciteJson.from_json(
            {'titles': ['not an object', {'title': 'kept'}], 'formats': ['text/csv', 7], 'publicationYear': '2021-05'}
        )
        self.assertEqual(datacite.titles, [{'title': 'kept'}])
        self.assertEqual(datacite.formats, ['text/csv'])
        self.assertEqual(datacite.publication_year, 2021)

    def test_from_json_accepts_a_missing_document(self):
        self.assertEqual(DataciteJson.from_json(None).titles, [])

    def test_subfield_values_collapses_whitespace_and_skips_blanks(self):
        entries = [{'subject': ' two  words\n'}, {'subject': '   '}, {'subject': 3}, {}]
        self.assertEqual(subfield_values(entries, 'subject'), ['two words'])

    def test_pick_titles_promotes_an_alternative_when_there_is_no_main_title(self):
        self.assertEqual(pick_titles([{'title': 'Alt', 'titleType': 'Subtitle'}]), ('Alt', []))

    def test_pick_titles_keeps_the_first_untyped_title_as_primary(self):
        titles = [{'title': 'Sub', 'titleType': 'Subtitle'}, {'title': 'Main'}, {'title': 'Main'}]
        self.assertEqual(pick_titles(titles), ('Main', ['Sub']))

    def test_sort_descriptions_puts_abstracts_first_then_the_longest(self):
        descriptions = [
            {'description': 'short methods', 'descriptionType': 'Methods'},
            {'description': 'a much longer other description', 'descriptionType': 'Other'},
            {'description': 'the abstract', 'descriptionType': 'Abstract'},
        ]
        self.assertEqual(
            sort_descriptions(descriptions),
            ['the abstract', 'a much longer other description', 'short methods'],
        )

    def test_pick_publication_date_prefers_issued_over_the_other_types(self):
        dates = [{'date': '2020-03-04', 'dateType': 'Updated'}, {'date': '2019-01-02', 'dateType': 'Issued'}]
        self.assertEqual(pick_publication_date(dates, 2021), date(2019, 1, 2))

    def test_pick_publication_date_falls_back_to_the_publication_year(self):
        self.assertEqual(pick_publication_date([{'date': 'not a date', 'dateType': 'Issued'}], 2021), date(2021, 1, 1))
        self.assertIsNone(pick_publication_date([], None))


class TestBuildDatasetRow(unittest.TestCase):
    def test_row_carries_the_datacite_fields_the_search_api_reads(self):
        row = build_dataset_row(
            record(
                datacite_json={
                    'titles': [{'title': 'Sea level rise'}, {'title': 'SLR', 'titleType': 'AlternativeTitle'}],
                    'descriptions': [{'description': 'An abstract.', 'descriptionType': 'Abstract'}],
                    'subjects': [{'subject': 'oceans', 'lang': 'EN'}, {'subject': 'oceans'}],
                    'creators': [{'creatorName': 'Doe, J.', 'nameIdentifiers': [{'nameIdentifier': '0000-0001'}]}],
                    'rightsList': [{'rights': 'CC-BY-4.0', 'rightsURI': 'https://x.org/by'}],
                    'publicationYear': 2020,
                }
            )
        )
        self.assertEqual(row.url, 'https://doi.org/10.5281/zenodo.1')
        self.assertEqual(row.doi, '10.5281/zenodo.1')
        self.assertEqual((row.title, row.alt_titles), ('Sea level rise', ['SLR']))
        self.assertEqual(row.description, 'An abstract.')
        self.assertEqual(row.keywords, ['oceans'])  # deduplicated
        self.assertEqual((row.creators, row.creator_identifiers), (['Doe, J.'], ['0000-0001']))
        self.assertEqual((row.license, row.license_url), ('CC-BY-4.0', 'https://x.org/by'))
        self.assertEqual(row.languages, ['en'])
        self.assertEqual((row.publication_year, row.publication_date), (2020, date(2020, 1, 1)))

    def test_search_text_holds_everything_bm25_should_match(self):
        row = build_dataset_row(
            record(
                datacite_json={
                    'titles': [{'title': 'Title'}],
                    'descriptions': [{'description': 'Body text.'}],
                    'subjects': [{'subject': 'keyword'}],
                    'creators': [{'creatorName': 'Doe, J.'}],
                }
            )
        )
        for expected in ('Title', 'Body text.', 'keyword', 'Doe, J.'):
            self.assertIn(expected, row.search_text)

    def test_title_falls_back_to_the_record_column(self):
        row = build_dataset_row(record(title='  From  the record ', datacite_json={}))
        self.assertEqual(row.title, 'From the record')

    def test_unindexable_without_a_doi_or_url(self):
        with self.assertRaises(UnindexableRecordError):
            build_dataset_row(record(doi=None, url=None))

    def test_unindexable_without_a_title(self):
        with self.assertRaises(UnindexableRecordError):
            build_dataset_row(record(title=None, datacite_json={}))

    def test_only_the_abstract_is_displayed_but_all_descriptions_are_embedded(self):
        row = build_dataset_row(
            record(
                datacite_json={
                    'titles': [{'title': 'Title'}],
                    'descriptions': [
                        {'description': 'The abstract.', 'descriptionType': 'Abstract'},
                        {'description': 'The methods.', 'descriptionType': 'Methods'},
                    ],
                }
            )
        )
        self.assertEqual(row.description, 'The abstract.')
        self.assertEqual(row.descriptions_text, 'The abstract.\n\nThe methods.')


class TestChunking(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(split_text('a short text'), ['a short text'])

    def test_split_respects_the_size_limit_and_word_boundaries(self):
        chunks = split_text(' '.join(['word'] * 2000))
        self.assertTrue(all(len(chunk) <= MAX_CHUNK_CHARS for chunk in chunks))
        self.assertTrue(all(chunk.split() == ['word'] * len(chunk.split()) for chunk in chunks))

    def test_split_stops_at_max_chunks(self):
        self.assertEqual(len(split_text('x' * 10 + ' ' + ' '.join(['word'] * 20000))), MAX_DESCRIPTION_CHUNKS)

    def test_chunks_are_named_per_field_and_indexed(self):
        row = build_dataset_row(
            record(
                datacite_json={
                    'titles': [{'title': 'Title'}],
                    'subjects': [{'subject': 'a'}, {'subject': 'b'}],
                    'descriptions': [{'description': 'Body.'}],
                }
            )
        )
        self.assertEqual(
            [(chunk.field_name, chunk.chunk_index, chunk.text) for chunk in dataset_chunks(row)],
            [('title', 0, 'Title'), ('keywords', 0, 'a, b'), ('description', 0, 'Body.')],
        )

    def test_empty_fields_produce_no_chunks(self):
        row = build_dataset_row(record(datacite_json={'titles': [{'title': 'Title'}]}))
        self.assertEqual([chunk.field_name for chunk in dataset_chunks(row)], ['title'])

    def test_a_long_title_is_never_split(self):
        row = build_dataset_row(record(datacite_json={'titles': [{'title': ' '.join(['word'] * 2000)}]}))
        self.assertEqual([chunk.field_name for chunk in dataset_chunks(row)], ['title'])


class TestBuildBatch(unittest.TestCase):
    def test_a_bad_record_is_skipped_without_losing_the_batch(self):
        rows, chunks = build_batch([record(doi=None, url=None), record(doi='10.5281/zenodo.2')])
        self.assertEqual([row.doi for row in rows], ['10.5281/zenodo.2'])
        self.assertTrue(chunks)

    def test_the_same_url_twice_in_a_batch_keeps_the_first(self):
        # the executemany upsert cannot update a row it inserted in the same statement
        rows, _ = build_batch(
            [
                record(source_record_id='a', datacite_json={'titles': [{'title': 'First'}]}),
                record(source_record_id='b', datacite_json={'titles': [{'title': 'Second'}]}),
            ]
        )
        self.assertEqual([row.title for row in rows], ['First'])


class TestNeedsIndexing(unittest.TestCase):
    def test_missing_or_outdated_records_need_indexing(self):
        newer = datetime(2026, 6, 1, tzinfo=UTC)
        self.assertTrue(needs_indexing('a', NOW, {}))
        self.assertTrue(needs_indexing('a', newer, {'a': NOW}))
        self.assertFalse(needs_indexing('a', NOW, {'a': NOW}))
        self.assertFalse(needs_indexing('a', NOW, {'a': newer}))


if __name__ == '__main__':
    unittest.main()
