import unittest
from unittest.mock import patch

from src.planning import file_sync_check as fsc


def make_endpoint(code='ZENODO', supported=True, uses_additional_metadata=True):
    return {
        'endpoint_id': 'endpoint-1',
        'harvest_url': 'https://example.org/oai',
        'code': code,
        'supported': supported,
        'uses_additional_metadata': uses_additional_metadata,
    }


class TestExtractorSupport(unittest.TestCase):
    def test_swiss_does_not_use_additional_metadata(self):
        self.assertEqual(fsc.extractor_support('SWISS', None), (True, False))

    def test_supported_codes(self):
        for code in fsc.EXTRACTOR_CODES:
            self.assertEqual(fsc.extractor_support(code, {}), (True, True), code)

    def test_unsupported_code(self):
        self.assertEqual(fsc.extractor_support('PANOSC', {}), (False, True))

    def test_dataverse_is_found_by_additional_metadata_params(self):
        params = {'additional_metadata_params': {'endpoint': 'https://dv/api', 'protocol': 'DATAVERSE_API'}}
        self.assertEqual(fsc.extractor_support('DANS', params), (True, True))

    def test_dataverse_needs_endpoint_and_protocol(self):
        self.assertEqual(
            fsc.extractor_support('DANS', {'additional_metadata_params': {'protocol': 'DATAVERSE_API'}}), (False, True)
        )
        self.assertEqual(
            fsc.extractor_support('DANS', {'additional_metadata_params': {'endpoint': 'https://dv/api'}}), (False, True)
        )


class TestClassifyRecord(unittest.TestCase):
    def test_buckets(self):
        cases = [
            # has_additional_metadata, has_files, supported, uses_additional_metadata, bucket
            (True, True, True, True, fsc.IN_SYNC),
            (True, False, True, True, fsc.POSSIBLE_SYNC_ISSUE),
            (False, False, True, True, fsc.EXPECTED_GAP),
            (False, True, True, True, fsc.UNEXPECTED_FILES),
            (True, False, False, True, fsc.UNSUPPORTED_PROVIDER),
            (True, True, False, True, fsc.IN_SYNC),
            (False, False, False, True, fsc.EXPECTED_GAP),
        ]
        for *args, bucket in cases:
            self.assertEqual(fsc.classify_record(*args), bucket, args)

    def test_swiss_has_always_input(self):
        self.assertEqual(fsc.classify_record(False, True, True, False), fsc.IN_SYNC)
        self.assertEqual(fsc.classify_record(False, False, True, False), fsc.POSSIBLE_SYNC_ISSUE)


class TestUpdateStats(unittest.TestCase):
    def test_counts_and_samples(self):
        endpoint = make_endpoint()
        stats = fsc.new_stats(endpoint)
        records = [
            {'record_identifier': 'a', 'has_additional_metadata': True},  # 2 files
            {'record_identifier': 'b', 'has_additional_metadata': True},  # no files: possible sync issue
            {'record_identifier': 'c', 'has_additional_metadata': True},  # no files: possible sync issue
            {'record_identifier': 'd', 'has_additional_metadata': False},  # expected gap
            {'record_identifier': 'e', 'has_additional_metadata': False},  # unexpected files
        ]

        fsc.update_stats(stats, endpoint, records, {'a': 2, 'e': 1}, sample_size=1)

        self.assertEqual(stats['records'], 5)
        self.assertEqual(stats['with_additional_metadata'], 3)
        self.assertEqual(stats['records_with_files'], 2)
        self.assertEqual(stats['file_rows'], 3)
        self.assertEqual(
            {bucket: stats[bucket] for bucket in fsc.BUCKETS},
            {
                fsc.IN_SYNC: 1,
                fsc.POSSIBLE_SYNC_ISSUE: 2,
                fsc.EXPECTED_GAP: 1,
                fsc.UNEXPECTED_FILES: 1,
                fsc.UNSUPPORTED_PROVIDER: 0,
            },
        )
        self.assertEqual(stats['samples'], ['b'])
        self.assertTrue(fsc.has_gaps(stats))

    def test_sample_size_zero(self):
        endpoint = make_endpoint()
        stats = fsc.new_stats(endpoint)
        fsc.update_stats(stats, endpoint, [{'record_identifier': 'a', 'has_additional_metadata': True}], {}, 0)
        self.assertEqual(stats['samples'], [])
        self.assertEqual(stats[fsc.POSSIBLE_SYNC_ISSUE], 1)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    """Answers the three queries of check_endpoint from in-memory data."""

    def __init__(self, records=None, files=None):
        self.records = records or []  # (record_identifier, has_additional_metadata), sorted
        self.files = files or {}  # record_identifier -> number of file rows
        self.record_queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        if 'FROM records' in query:
            _, last_identifier, limit = params
            self.record_queries.append(last_identifier)
            rows = [
                {'record_identifier': identifier, 'has_additional_metadata': has_additional}
                for identifier, has_additional in self.records
                if identifier > last_identifier
            ]
            return FakeCursor(rows[:limit])

        harvest_url, identifiers = params
        self.assert_file_lookup(harvest_url)
        return FakeCursor(
            [{'record_identifier': i, 'files': self.files[i]} for i in identifiers if self.files.get(i, 0) > 0]
        )

    def assert_file_lookup(self, harvest_url):
        assert harvest_url == 'https://example.org/oai'


class TestCheckEndpoint(unittest.TestCase):
    def test_batches_cover_all_records(self):
        records = [(f'id-{n}', n % 2 == 0) for n in range(5)]
        datasets = FakeConnection(records=records)
        files = FakeConnection(files={'id-0': 3, 'id-1': 1})

        with (
            patch.object(fsc.psycopg, 'connect', side_effect=[datasets, files]),
            patch.object(fsc, 'PostgresConfig'),
            patch.object(fsc, 'file_db_config'),
        ):
            stats = fsc.check_endpoint(make_endpoint(), batch_size=2, sample_size=10)

        # 5 records in batches of 2: three queries with data and a fourth that ends the loop
        self.assertEqual(datasets.record_queries, ['', 'id-1', 'id-3', 'id-4'])
        self.assertEqual(stats['records'], 5)
        self.assertEqual(stats['records_with_files'], 2)
        self.assertEqual(stats['file_rows'], 4)
        self.assertEqual(stats[fsc.IN_SYNC], 1)  # id-0
        self.assertEqual(stats[fsc.UNEXPECTED_FILES], 1)  # id-1: files without additional metadata
        self.assertEqual(stats[fsc.POSSIBLE_SYNC_ISSUE], 2)  # id-2, id-4
        self.assertEqual(stats[fsc.EXPECTED_GAP], 1)  # id-3
        self.assertEqual(stats['samples'], ['id-2', 'id-4'])

    def test_endpoint_without_records(self):
        with (
            patch.object(fsc.psycopg, 'connect', side_effect=[FakeConnection(), FakeConnection()]),
            patch.object(fsc, 'PostgresConfig'),
            patch.object(fsc, 'file_db_config'),
        ):
            stats = fsc.check_endpoint(make_endpoint(), batch_size=10, sample_size=10)

        self.assertEqual(stats['records'], 0)
        self.assertFalse(fsc.has_gaps(stats))


class TestFileDbConfig(unittest.TestCase):
    def test_requires_file_db(self):
        with patch.dict(fsc.os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                fsc.file_db_config()


class TestReport(unittest.TestCase):
    def make_results(self):
        clean, gaps = make_endpoint(), make_endpoint(code='MDDB')
        gaps['harvest_url'] = 'https://mdposit.example/v2'

        ok_stats = fsc.new_stats(clean)
        fsc.update_stats(ok_stats, clean, [{'record_identifier': 'a', 'has_additional_metadata': True}], {'a': 1}, 10)

        gap_stats = fsc.new_stats(gaps)
        fsc.update_stats(gap_stats, gaps, [{'record_identifier': 'x', 'has_additional_metadata': True}], {}, 10)

        return [ok_stats, gap_stats]

    def test_report_contains_all_endpoints_and_total(self):
        report = fsc.format_report(self.make_results(), only_gaps=False)

        self.assertIn('ZENODO  https://example.org/oai', report)
        self.assertIn('MDDB  https://mdposit.example/v2', report)
        self.assertIn('examples of possible_sync_issue: x', report)
        self.assertIn('TOTAL (2 endpoints): records: 2, records with files: 1 (50.0%), file rows: 1', report)

    def test_only_gaps(self):
        report = fsc.format_report(self.make_results(), only_gaps=True)

        self.assertNotIn('ZENODO', report)
        self.assertIn('MDDB', report)
        self.assertIn('TOTAL (2 endpoints)', report)

    def test_only_gaps_without_gaps(self):
        report = fsc.format_report(self.make_results()[:1], only_gaps=True)

        self.assertIn('No endpoint with possible sync issues', report)

    def test_unsupported_provider_is_marked(self):
        endpoint = make_endpoint(code='PANOSC', supported=False)
        self.assertIn('(file extractor: unsupported)', fsc.format_endpoint(fsc.new_stats(endpoint)))
