import unittest
from unittest.mock import patch

from src.planning import opensearch_sync


def make_row(n, datacite_json='default'):
    if datacite_json == 'default':
        datacite_json = {'url': f'https://example.org/{n}', 'emb': None}
    return {
        'id': f'id-{n}',
        'record_identifier': f'oai:example:{n}',
        'datacite_json': datacite_json,
        'embeddings': [0.1 * n, 0.2 * n],
        'code': 'REPO',
        'harvest_url': 'https://example.org/oai',
    }


class TestRowToSource(unittest.TestCase):
    def test_structure(self):
        self.assertEqual(
            opensearch_sync.row_to_source(make_row(1)),
            {
                'url': 'https://example.org/1',
                'emb': [0.1, 0.2],
                '_repo': 'REPO',
                '_harvest_url': 'https://example.org/oai',
                '_record_identifier': 'oai:example:1',
            },
        )

    def test_embeddings_column_replaces_emb_of_json(self):
        row = make_row(1)
        row['datacite_json']['emb'] = [9.9]
        self.assertEqual(opensearch_sync.row_to_source(row)['emb'], [0.1, 0.2])

    def test_without_datacite_json(self):
        self.assertIsNone(opensearch_sync.row_to_source(make_row(1, datacite_json=None)))


class TestToBulkActions(unittest.TestCase):
    def test_action_structure(self):
        source = {'url': 'https://example.org/1', 'titles': []}
        self.assertEqual(
            opensearch_sync.to_bulk_actions([source], 'idx'),
            [{'_op_type': 'index', '_id': 'https://example.org/1', '_index': 'idx', '_source': source}],
        )


class TestCreateIndex(unittest.TestCase):
    @patch('src.planning.opensearch_sync._client')
    def test_aborts_if_index_exists(self, client_factory):
        client = client_factory.return_value
        client.indices.exists.return_value = True

        with self.assertRaises(ValueError):
            opensearch_sync.create_index('idx', 384)

        client.indices.create.assert_not_called()
        client.close.assert_called_once()

    @patch('src.planning.opensearch_sync._client')
    def test_creates_index_with_dimension(self, client_factory):
        client = client_factory.return_value
        client.indices.exists.return_value = False

        opensearch_sync.create_index('idx', 384)

        client.indices.create.assert_called_once()
        kwargs = client.indices.create.call_args.kwargs
        self.assertEqual(kwargs['index'], 'idx')
        self.assertEqual(kwargs['body']['mappings']['properties']['emb']['dimension'], 384)
        client.close.assert_called_once()


class TestSyncRecords(unittest.TestCase):
    @patch('src.planning.opensearch_sync.PostgresConfig')
    @patch('src.planning.opensearch_sync.bulk')
    @patch('src.planning.opensearch_sync.psycopg.connect')
    @patch('src.planning.opensearch_sync._client')
    def test_keyset_pagination_and_actions(self, _client, connect, bulk, _postgres_config):
        # 5 rows, one without datacite_json, batch size 2 -> 3 batches, then an empty page ends the loop
        pages = [
            [make_row(1), make_row(2)],
            [make_row(3), make_row(4, datacite_json=None)],
            [make_row(5)],
            [],
        ]
        conn = connect.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.side_effect = pages
        bulk.side_effect = lambda client, actions: (len(list(actions)), [])

        indexed = opensearch_sync.sync_records('idx', 2)

        self.assertEqual(indexed, 4)
        # keyset: every query continues after the last id of the previous page
        self.assertEqual(
            [call.args[1] for call in conn.execute.call_args_list],
            [('', 2), ('id-2', 2), ('id-4', 2), ('id-5', 2)],
        )
        # the documents are the bulk actions of the transform (_id is the url)
        first_actions = bulk.call_args_list[0].args[1]
        self.assertEqual(first_actions[0]['_id'], 'https://example.org/1')
        self.assertEqual(first_actions[0]['_index'], 'idx')
        self.assertEqual(first_actions[0]['_source']['_repo'], 'REPO')
        _client.return_value.close.assert_called_once()

    def test_invalid_batch_size(self):
        with self.assertRaises(ValueError):
            opensearch_sync.sync_records('idx', 0)


if __name__ == '__main__':
    unittest.main()
