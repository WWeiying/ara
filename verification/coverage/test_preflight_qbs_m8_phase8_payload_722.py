import copy
import struct
import unittest

import preflight_qbs_m8_phase8_payload_722 as p


class PreflightTests(unittest.TestCase):
    def test_seven_interior_boundaries_all_four_bank1_contexts(self):
        for boundary in range(32, 256, 32):
            events = p.crossing(8, boundary)
            self.assertEqual([e['pending_byte'] for e in events], [12, 13, 14, 15])
            self.assertEqual([e['old_byte'] for e in events], [4, 5, 6, 7])
            self.assertTrue(all(e['pending_word'] == e['old_word']+1 for e in events))

    def test_phase4_is_distinct_and_phase0_has_no_bank1_crossing(self):
        self.assertEqual([e['pending_byte'] for e in p.crossing(4)], [8, 9, 10, 11])
        self.assertEqual(p.crossing(0), [])
        self.assertEqual(p.crossing(12), [])

    def test_unaligned_phase_rejected(self):
        with self.assertRaisesRegex(ValueError, 'alignment'):
            p.crossing(13)

    def test_native_unpack_mac(self):
        weight, rows, packed = p.native_fixture()
        self.assertEqual(len(packed), 2336)
        self.assertEqual([p.native_dot(weight, row) for row in rows],
                         [struct.unpack('<I', struct.pack('<f', 256*(i+1)))[0] for i in range(8)])

    def test_changed_quant_and_bsum_rejected(self):
        weight, rows, _ = p.native_fixture()
        row = bytearray(rows[0]); row[4] ^= 1
        with self.assertRaisesRegex(ValueError, 'bsum'):
            p.native_dot(weight, row)
        row = bytearray(rows[0]); row[260] ^= 1
        with self.assertRaisesRegex(ValueError, 'bsum'):
            p.native_dot(weight, row)

    def test_changed_weight_changes_oracle(self):
        weight, rows, _ = p.native_fixture()
        mutated = bytearray(weight); mutated[48] ^= 1
        self.assertNotEqual(p.native_dot(weight, rows[0]), p.native_dot(mutated, rows[0]))

    def test_independent_m8_inverse(self):
        _, rows, packed = p.native_fixture()
        for context in range(8):
            scale = packed[context*4:context*4+4]
            quants = bytes(packed[32+8*k+context] for k in range(256))
            sums = b''.join(packed[2080+16*k+2*context:2082+16*k+2*context] for k in range(16))
            self.assertEqual(scale+quants+sums, rows[context])

    def test_coordinate_mutations_rejected(self):
        expected = p.TARGETS[0]
        point = dict(raw_index=6475, native_id='2884', line='219', vector='111',
                     spec=dict(generate_info='slot=0,p=2,r=0,b=12'),
                     attributes=dict(condregid='2884'))
        p.validate_point(point, expected, 0)
        for key, value in [('raw_index', 6476), ('native_id', '2885'),
                           ('line', '223'), ('vector', '110')]:
            changed = copy.deepcopy(point); changed[key] = value
            with self.assertRaises(ValueError):
                p.validate_point(changed, expected, 0)
        changed = copy.deepcopy(point); changed['spec']['generate_info'] = 'slot=1,p=2,r=0,b=12'
        with self.assertRaises(ValueError):
            p.validate_point(changed, expected, 0)


if __name__ == '__main__':
    unittest.main()
