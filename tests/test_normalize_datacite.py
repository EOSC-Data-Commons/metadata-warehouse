import unittest
import json
from src.utils import normalize_datacite_json


class TestNormalizeDatacite(unittest.TestCase):

    def test_make_array_from_object(self):
        with open('tests/testdata/doi_10.17026_dans-2ab-dpmm.oai_datacite.xml.json') as f:
            data = json.load(f)['http://www.openarchives.org/OAI/2.0/:record'][
                'http://www.openarchives.org/OAI/2.0/:metadata']['http://datacite.org/schema/kernel-4:resource']
        res = normalize_datacite_json.make_array(data.get('http://datacite.org/schema/kernel-4:titles'),
                                                 'http://datacite.org/schema/kernel-4:title')

        self.assertEqual(len(res), 1)
        self.assertTrue(res[0].get('http://datacite.org/schema/kernel-4:title'))

    def test_make_array_from_field_list(self):
        with open('tests/testdata/doi_10.17026_SS_78HHDK.oai_datacite.xml.json') as f:
            data = json.load(f)['http://www.openarchives.org/OAI/2.0/:record'][
                'http://www.openarchives.org/OAI/2.0/:metadata']['http://datacite.org/schema/kernel-4:resource']
        res = normalize_datacite_json.make_array(data.get('http://datacite.org/schema/kernel-4:titles'),
                                                 'http://datacite.org/schema/kernel-4:title')

        # print(res)
        self.assertEqual(len(res), 2)
        self.assertTrue(res[0].get('http://datacite.org/schema/kernel-4:title'))
        self.assertTrue(res[1].get('http://datacite.org/schema/kernel-4:title'))

    def test_harmonize_props_string(self):
        data = {
            'http://datacite.org/schema/kernel-4:title': 'A title'
        }

        res = normalize_datacite_json.harmonize_props(data, 'http://datacite.org/schema/kernel-4:title', {}, {})

        # print(res)

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

        res = normalize_datacite_json.harmonize_props(data, 'http://datacite.org/schema/kernel-4:title',
                                                      {'@titleType': 'titleType'}, {})

        # print(res)

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
                {'http://datacite.org/schema/kernel-4:creatorName': {'#text': 'Pe\u0161un, Luka',
                                                                     '@nameType': 'personal'}}
        }

        res = normalize_datacite_json.harmonize_creator(data)

        self.assertEqual(res, {'creatorName': 'Pe\u0161un, Luka', 'nameType': 'personal'})

    def test_normalize_date_precision_with_day_precision(self):
        res = normalize_datacite_json.normalize_date_precision('2025-04-03')
        self.assertEqual(res, '2025-04-03')

    def test_normalize_date_precision_with_month_precision(self):
        res = normalize_datacite_json.normalize_date_precision('2025-04')
        self.assertEqual(res, '2025-04-01')

    def test_normalize_date_precision_with_year_precision(self):
        res = normalize_datacite_json.normalize_date_precision('2025')
        self.assertEqual(res, '2025-01-01')

    def test_normalize_date_precision_with_month_without_leading_zero(self):
        res = normalize_datacite_json.normalize_date_precision('2019-6-01')
        self.assertEqual(res, '2019-06-01')

    def test_normalize_date_precision_with_day_without_leading_zero(self):
        res = normalize_datacite_json.normalize_date_precision('2019-07-5')
        self.assertEqual(res, '2019-07-05')

    def test_normalize_date_precision_with_day_without_leading_zer2(self):
        res = normalize_datacite_json.normalize_date_precision('2019-11-5')
        self.assertEqual(res, '2019-11-05')

    def test_normalize_date_precision_with_month_and_day_without_leading_zero(self):
        res = normalize_datacite_json.normalize_date_precision('2019-7-9')
        self.assertEqual(res, '2019-07-09')

    def test_normalize_date_string_with_single_date(self):
        res = normalize_datacite_json.normalize_date_string('2025-06-07')
        self.assertEqual(res, '2025-06-07')

    def test_normalize_date_string_with_period(self):
        res = normalize_datacite_json.normalize_date_string('2025/2026')
        self.assertEqual(res, '2025-01-01')

    def test_normalize_date_string_with_datetime(self):
        res = normalize_datacite_json.normalize_date_string('2025-08-05 09:35:06')
        self.assertEqual(res, '2025-08-05')

    def test_make_id_with_url(self):
        res = normalize_datacite_json.make_id({'url': 'https://example.com'})
        self.assertEqual(res, 'https://example.com')

    def test_make_id_with_doi(self):
        res = normalize_datacite_json.make_id({'doi': '10.123/123'})
        self.assertEqual(res, 'https://doi.org/10.123/123')

    def test_get_resource_type_with_text_node(self):
        test_res = {
            'http://datacite.org/schema/kernel-4:resourceType': {
                '@resourceTypeGeneral': 'Dataset',
                '#text': 'test'
            }
        }

        res = normalize_datacite_json.get_resource_type(test_res)

        self.assertEqual(res,
                         {'resourceType': 'test', 'resourceTypeGeneral': 'Dataset'}
                         )

    def test_get_resource_type_without_text_node(self):
        test_res = {
            'http://datacite.org/schema/kernel-4:resourceType': {
                '@resourceTypeGeneral': 'Dataset'
            }
        }

        res = normalize_datacite_json.get_resource_type(test_res)

        self.assertEqual(res,
                         {'resourceTypeGeneral': 'Dataset'}
                         )

    def test_normalize_lang_string_with_three_char_string(self):
        res = normalize_datacite_json.normalize_lang_string('eng')

        self.assertEqual(res, 'en')

    def test_normalize_lang_string_with_two_char_string(self):
        res = normalize_datacite_json.normalize_lang_string('en')

        self.assertEqual(res, 'en')
