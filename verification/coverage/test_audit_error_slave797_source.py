import unittest
import audit_error_slave797_source as a


class ConstantBoundary(unittest.TestCase):
    def test_actual_frozen_packet(self):
        packet = a.collect()
        self.assertEqual(packet['candidate_slots'], 1452)
        self.assertEqual(len(packet['targets']), 7)
        self.assertEqual([t['candidate_slots'] for t in packet['targets']],
                         [188, 188, 188, 256, 188, 256, 188])
        self.assertFalse(packet['EDA_started'])
        self.assertFalse(packet['EL_generated'])

    def test_direct_includes_ones(self):
        self.assertEqual(a.constant_bits(True), list(range(128)))

    def test_filter_protects_34_ones(self):
        bits = a.constant_bits(False)
        self.assertEqual(len(bits), 94)
        self.assertTrue(set(range(64, 128)) <= set(bits))
        self.assertTrue(all(not (a.VALUE >> b & 1) for b in bits))

    def test_ones_cannot_be_filtered_constants(self):
        self.assertNotIn(1, a.constant_bits(False))

    def test_bad_width(self):
        with self.assertRaises(ValueError):
            a.constant_bits(False, width=64)

    def test_unsigned_overflow(self):
        with self.assertRaises(ValueError):
            a.constant_bits(True, value=2**64)

    def test_pair_mapping(self):
        n = dict(left='127', right='0', logical_width=128, serialized_offset=718)
        self.assertEqual(a.coordinates(n, [0, 64]), [718, 719, 846, 847])

    def test_serialized_msb_first(self):
        a.zero_pairs(dict(width=4, bits='0x3'), [0, 1])
        with self.assertRaises(ValueError):
            a.zero_pairs(dict(width=4, bits='0x3'), [2, 3])

    def test_serialized_bounds(self):
        with self.assertRaises(ValueError):
            a.zero_pairs(dict(width=4, bits='0x0'), [4])

    def test_ancestor_scope_exclusion(self):
        with self.assertRaises(ValueError):
            a.overlap('a.b.c', 'r.data', [0], {('a.b', '', '', 'WHOLE_SCOPE')}, {})

    def test_single_direction_overlap_rejected(self):
        with self.assertRaises(ValueError):
            a.overlap('a', 'r.data', [0], set(), {('a', '', 'r.data', '', '', (), '0to1'): 1})

    def test_opaque_toggle_hold(self):
        with self.assertRaises(ValueError):
            a.overlap('a', 'r.data', [0], {('a', '', '', 'Toggle unknown')}, {})

    def test_exact_array_index(self):
        self.assertEqual(a.overlap('a', 'mst_resps_i[1].r.data', [0], set(),
            {('a', '', 'mst_resps_i[0].r.data', '', '', (), '0to1'): 1}), {'0to1': [], '1to0': []})


if __name__ == '__main__':
    unittest.main()
