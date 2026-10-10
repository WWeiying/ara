import copy
import json
import unittest

import build_cache_port1_sv39_preflight as m


class BoundaryTests(unittest.TestCase):
    def test_independent_word_unsigned64(self):
        self.assertEqual(m.word(0), 0x13579bdf2468ace0)
        for i in range(64):
            self.assertTrue(0 <= m.word(i) < 1 << 64)
        self.assertEqual(len({m.word(i) for i in range(64)}), 64)

    def test_actual715_targets_zero(self):
        bitmap = json.loads((m.BASE / 'combined-bits.json').read_bytes())
        self.assertEqual(len(m.targets(bitmap)), 5)

    def test_hit_target_not_claimed_zero(self):
        bitmap = json.loads((m.BASE / 'combined-bits.json').read_bytes())
        row = bitmap['metrics']['fsm'][m.C]
        row['bits'] = hex(int(row['bits'], 16) | (1 << (row['width'] - 1 - 6)))
        with self.assertRaises(ValueError):
            m.targets(bitmap)

    def test_target_shape_mismatch_rejected(self):
        bitmap = json.loads((m.BASE / 'combined-bits.json').read_bytes())
        bitmap['metrics']['branch'][m.C]['checksum'] = '0'
        with self.assertRaises(ValueError):
            m.targets(bitmap)

    def test_pte_pair_and_load_window_layout(self):
        text = m.APP.read_text()
        self.assertIn('.space 3840', text)
        self.assertIn('.rept 56', text)
        self.assertEqual(3840 + 56 * 4 + 8 * 4, 4096)
        self.assertNotIn('vsseg', text)
        self.assertIn('p ? 33 : 1', text)
        self.assertIn('aligned(4)', text)

    def test_no_replay_claim_in_static_target_inventory(self):
        bitmap = json.loads((m.BASE / 'combined-bits.json').read_bytes())
        self.assertTrue(all(not r['native_exclusion_identity_claimed'] for r in m.targets(bitmap)))


if __name__ == '__main__':
    unittest.main()
