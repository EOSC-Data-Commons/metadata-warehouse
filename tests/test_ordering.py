import unittest

from src.planning.ordering import split_by_dependency


def run(url, due=True, depends_on=None):
    return {'harvest_url': url, 'should_be_harvested': due, 'depends_on_endpoint_id': depends_on}


class TestSplitByDependency(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(split_by_dependency([]), ([], []))

    def test_dependent_endpoints_are_separated_and_order_is_kept(self):
        runs = [run('zenodo', depends_on='hal-id'), run('a'), run('hal'), run('dryad', depends_on='x'), run('b')]
        self.assertEqual(split_by_dependency(runs), (['a', 'hal', 'b'], ['zenodo', 'dryad']))

    def test_endpoints_not_due_are_skipped(self):
        self.assertEqual(split_by_dependency([run('a', due=False), run('b')]), (['b'], []))

    def test_entries_without_url_are_skipped(self):
        self.assertEqual(split_by_dependency([run(None), run('b')]), (['b'], []))


if __name__ == '__main__':
    unittest.main()
