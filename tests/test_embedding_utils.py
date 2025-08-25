import unittest
import json
from src.utils import embedding_utils

class TestEmbeddingsUtils(unittest.TestCase):

    def test_get_embedding_text_from_fields(self):
        with open('tests/testdata/doi_10.17026_SS_78HHDK.oai_datacite_normalized.xml.json') as f:
            data = json.load(f)

        res = embedding_utils.get_embedding_text_from_fields(data)

        self.assertTrue(len(res) > 0)
