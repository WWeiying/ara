"""Negative checks for exact native-index selection, not DUT verification."""
import copy
import unittest

from prepare_gap38_queue_batch import missing_targets


class QueueSelectionTest(unittest.TestCase):
    def setUp(self):
        self.candidate = {'scope': 'queue', 'branch': {'raw_index': 41},
                          'blocks': [{'index': '120'}, {'index': '121'}]}
        self.bits = {'metrics': {m: {'queue': {'checksum': m, 'width': w, 'bits': '0'}}
                                for m, w in [('branch', 128), ('line', 160)]}}
        self.old = copy.deepcopy(self.bits)

    def test_missing(self):
        self.assertEqual(missing_targets(self.bits, self.old, self.candidate)
                         ['still_missing_raw_indices'], {'branch': [41], 'line': [120, 121]})

    def test_hit_in_native_string_order(self):
        self.bits['metrics']['branch']['queue']['bits'] = hex(1 << (128 - 1 - 41))
        with self.assertRaises(Exception):
            missing_targets(self.bits, self.old, self.candidate)

    def test_neighbor_does_not_exclude_target(self):
        self.bits['metrics']['branch']['queue']['bits'] = hex(1 << (128 - 1 - 42))
        missing_targets(self.bits, self.old, self.candidate)

    def test_shape_drift(self):
        self.bits['metrics']['line']['queue']['checksum'] = 'other'
        with self.assertRaises(Exception):
            missing_targets(self.bits, self.old, self.candidate)

    def test_malformed_bits(self):
        self.bits['metrics']['line']['queue']['bits'] = hex(1 << 160)
        with self.assertRaises(Exception):
            missing_targets(self.bits, self.old, self.candidate)

    def test_coordinate_drift(self):
        self.candidate['blocks'][1]['index'] = '122'
        with self.assertRaises(Exception):
            missing_targets(self.bits, self.old, self.candidate)


if __name__ == '__main__':
    unittest.main()
