import copy
import unittest

from src.utils.opensearch_utils import make_opensearch_document


class TestMakeOpensearchDocument(unittest.TestCase):
    def test_sets_metadata_fields(self):
        self.assertEqual(
            make_opensearch_document(
                src={'url': 'https://example.org/1', 'titles': []},
                repository='REPO',
                harvest_url='https://example.org/oai',
                record_identifier='oai:example:1',
            ),
            {
                'url': 'https://example.org/1',
                'titles': [],
                '_repo': 'REPO',
                '_harvest_url': 'https://example.org/oai',
                '_record_identifier': 'oai:example:1',
            },
        )

    def test_overrides_stale_metadata_fields_of_src(self):
        # datacite_json of the records table already contains these fields, with the values of the time of the harvest
        document = make_opensearch_document(
            src={'_repo': 'OLD', '_harvest_url': 'https://old.example.org/oai', '_record_identifier': 'old'},
            repository='REPO',
            harvest_url='https://example.org/oai',
            record_identifier='oai:example:1',
        )

        self.assertEqual(document['_repo'], 'REPO')
        self.assertEqual(document['_harvest_url'], 'https://example.org/oai')
        self.assertEqual(document['_record_identifier'], 'oai:example:1')

    def test_src_is_not_modified(self):
        src = {'url': 'https://example.org/1'}
        expected = copy.deepcopy(src)

        make_opensearch_document(src, 'REPO', 'https://example.org/oai', 'oai:example:1')

        self.assertEqual(src, expected)


if __name__ == '__main__':
    unittest.main()
