import unittest
import inspect_cva6_mda767 as r


class IntervalTests(unittest.TestCase):
    def test_exact_large_array(self):
        dims, size = r.dimensions(dict(packedrange='31 0 63 0', unpackedrange=''))
        self.assertEqual(size, 2048)
        self.assertEqual(len(dims), 2)
        group = r.intervals('0 64 0 64 1984 14 -1')[0]
        self.assertEqual(group['extent'], size)
        self.assertEqual(group['raw_code_counts'], {0: 64, 14: 1984})

    def test_bad_intervals(self):
        for value in ('0 64 14', '0 64 -1', '1 64 14 -1', '0 64 14 63 1 0 -1', '0 0 14 -1', '-1'):
            with self.subTest(value=value), self.assertRaises(ValueError): r.intervals(value)

    def test_no_direction_inference(self):
        self.assertEqual(r.intervals('0 1 4 1 1 10 -1')[0]['raw_code_counts'], {4: 1, 10: 1})

    def test_malformed_dimensions(self):
        for dims in ('', '31 0 63'):
            with self.assertRaises(ValueError): r.dimensions(dict(packedrange=dims))


if __name__ == '__main__': unittest.main()
