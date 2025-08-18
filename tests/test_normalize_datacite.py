import unittest
import json
from src.utils import normalize_datacite_json


class TestNormalizeDatacite(unittest.TestCase):

    def test_make_array_from_object(self):
        with open('tests/testdata/doi_10.17026_dans-2ab-dpmm.oai_datacite.xml.json') as f:
            data = json.load(f)['http://www.openarchives.org/OAI/2.0/:record'][
                'http://www.openarchives.org/OAI/2.0/:metadata']['http://datacite.org/schema/kernel-4:resource']
        res = normalize_datacite_json.make_array(data.get('http://datacite.org/schema/kernel-4:titles'), 'http://datacite.org/schema/kernel-4:title')

        self.assertEqual(len(res),1)
        self.assertTrue(res[0].get('http://datacite.org/schema/kernel-4:title'))


    def test_make_array_from_field_list(self):
        with open('tests/testdata/doi_10.17026_SS_78HHDK.oai_datacite.xml.json') as f:
            data = json.load(f)['http://www.openarchives.org/OAI/2.0/:record'][
                'http://www.openarchives.org/OAI/2.0/:metadata']['http://datacite.org/schema/kernel-4:resource']
        res = normalize_datacite_json.make_array(data.get('http://datacite.org/schema/kernel-4:titles'), 'http://datacite.org/schema/kernel-4:title')

        #print(res)
        self.assertEqual(len(res), 2)
        self.assertTrue(res[0].get('http://datacite.org/schema/kernel-4:title'))
        self.assertTrue(res[1].get('http://datacite.org/schema/kernel-4:title'))

    def test_harmonize_props_string(self):
        data = {
            'http://datacite.org/schema/kernel-4:title': 'A title'
        }

        res = normalize_datacite_json.harmonize_props(data, 'http://datacite.org/schema/kernel-4:title', {})

        #print(res)

        self.assertEqual(res, {
            'title': 'A title'
        })

    def test_harmonize_props_object(self):
        data = {
            'http://datacite.org/schema/kernel-4:title': {
                '#text': 'Another title',
                '@titleType': 'alternative'
            }
        }

        res = normalize_datacite_json.harmonize_props(data, 'http://datacite.org/schema/kernel-4:title', {'@titleType': 'titleType'})

        #print(res)

        self.assertEqual(res, {
            'title': 'Another title',
            'titleType': 'alternative'
        })

    def test_harmonize_creator_string(self):
        data = {
            'http://datacite.org/schema/kernel-4:creator':
                {'http://datacite.org/schema/kernel-4:creatorName': 'Pe\u0161un, Luka'}
        }

        res = normalize_datacite_json.harmonize_creator(data)

        self.assertEqual(res, {'creatorName': 'Pe\u0161un, Luka'})

    def test_harmonize_creator_object(self):
        data = {
            'http://datacite.org/schema/kernel-4:creator':
                {'http://datacite.org/schema/kernel-4:creatorName': {'#text': 'Pe\u0161un, Luka', '@nameType': 'personal'}}
        }

        res = normalize_datacite_json.harmonize_creator(data)

        self.assertEqual(res, {'creatorName': 'Pe\u0161un, Luka', 'nameType': 'personal'})


