import unittest

from src.planning.batching import BatchRange, chunk_ranges


class TestChunkRanges(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(chunk_ranges([], 3), [])

    def test_exact_multiple(self):
        self.assertEqual(
            chunk_ranges(['a', 'b', 'c', 'd'], 2),
            [BatchRange('a', 'b', 2), BatchRange('c', 'd', 2)],
        )

    def test_last_batch_smaller(self):
        self.assertEqual(
            chunk_ranges(['a', 'b', 'c', 'd', 'e'], 2),
            [BatchRange('a', 'b', 2), BatchRange('c', 'd', 2), BatchRange('e', 'e', 1)],
        )

    def test_fewer_ids_than_batch_size(self):
        self.assertEqual(chunk_ranges(['a', 'b'], 250), [BatchRange('a', 'b', 2)])

    def test_works_with_generators(self):
        self.assertEqual(
            chunk_ranges((x for x in 'abc'), 1),
            [BatchRange('a', 'a', 1), BatchRange('b', 'b', 1), BatchRange('c', 'c', 1)],
        )

    def test_invalid_batch_size(self):
        with self.assertRaises(ValueError):
            chunk_ranges(['a'], 0)


if __name__ == '__main__':
    unittest.main()
