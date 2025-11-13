import datetime
import unittest
from pathlib import Path
from unittest.mock import MagicMock
import json
from src.utils import embedding_utils
from fastembed import TextEmbedding
import numpy as np

from src.utils.embedding_utils import SourceWithEmbeddingText
from src.utils.queue_utils import HarvestEventQueue


class TestEmbeddingsUtils(unittest.TestCase):

    def test_get_embedding_text_from_fields(self):
        with open('tests/testdata/doi_10.17026_SS_78HHDK.oai_datacite_normalized.xml.json') as f:
            data = json.load(f)

        res = embedding_utils.get_embedding_text_from_fields(data)

        self.assertTrue(len(res) > 0)
        self.assertTrue('Social Sciences' in res)
        self.assertTrue('consumentenopvattingen' in res)
        self.assertTrue('Consumentenconjunctuuronderzoek' in res)

    def test_add_embeddings_to_source(self):
        embedding_model = TextEmbedding()
        embedding_model.embed = MagicMock(name='embed') # mock embed method
        embedding_model.embed.return_value = [np.array([1, 2, 3]), np.array([4, 5, 6]), np.array([7, 8, 9])]

        data = [SourceWithEmbeddingText(
            src={
                'titles': ['a title']
            },
            textToEmbed='a title',
            event=HarvestEventQueue(
                id='1',
                xml='<root></root',
                repository_id='1',
                endpoint_id='2',
                record_identifier='xyz',
                code='DANS',
                harvest_url='https://oai.org',
                additional_metadata='{}',
                is_deleted=False,
                datestamp='2025-11-13T14:50:35.397Z'
            )
        ), SourceWithEmbeddingText(
            src={
                'titles': ['a title 1']
            },
            textToEmbed='a title 1',
            event=HarvestEventQueue(
                id='2',
                xml='<root></root',
                repository_id='1',
                endpoint_id='2',
                record_identifier='xyz',
                code='DANS',
                harvest_url='https://oai.org',
                additional_metadata='{}',
                is_deleted=False,
                datestamp='2025-11-13T14:50:35.397Z'
            )
        ), SourceWithEmbeddingText(
            src={
                'titles': ['a title 2']
            },
            textToEmbed='a title 2',
            event=HarvestEventQueue(
                id='3',
                xml='<root></root',
                repository_id='1',
                endpoint_id='2',
                record_identifier='xyz',
                code='DANS',
                harvest_url='https://oai.org',
                additional_metadata='{}',
                is_deleted=False,
                datestamp='2025-11-13T14:50:35.397Z'
            )
        )]
        res = embedding_utils.add_embeddings_to_source(data, embedding_model)

        self.assertEqual(len(res), 3)

        self.assertEqual(res[0][0]['titles'][0], 'a title')
        self.assertEqual(res[0][0]['emb'], [1,2,3])
        self.assertEqual(res[0][1].event.id, '1')

        self.assertEqual(res[1][0]['titles'][0], 'a title 1')
        self.assertEqual(res[1][0]['emb'], [4, 5, 6])
        self.assertEqual(res[1][1].event.id, '2')

        self.assertEqual(res[2][0]['titles'][0], 'a title 2')
        self.assertEqual(res[2][0]['emb'], [7, 8, 9])
        self.assertEqual(res[2][1].event.id, '3')
