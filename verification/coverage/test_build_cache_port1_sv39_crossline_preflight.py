import copy
import json
import unittest

import build_cache_port1_sv39_crossline_preflight as m


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
        self.assertIn('p ? 35 : 3', text)
        self.assertIn('aligned(4)', text)

    def test_frozen_config_is32bytes(self):
        self.assertEqual(m.configuration_proof()['line_bytes'], 32)

    def geometry_fixture(self):
        symbols = dict(gcb_leaf=0x80010000, gcb_root=0x80011000,
                       gcb_mid=0x80012000, gcb_data=0x80013000,
                       gcb_page=0x80020000, gcb_second=0x80021000)
        writes = {symbols['gcb_root'] + 8: ((symbols['gcb_mid'] >> 12) << 10) | 1,
                  symbols['gcb_mid']: ((symbols['gcb_leaf'] >> 12) << 10) | 1}
        for slot in (3, 35):
            for i, name in enumerate(('gcb_page', 'gcb_second')):
                writes[symbols['gcb_leaf'] + (slot + i) * 8] = ((symbols[name] >> 12) << 10) | 0xcb
        return symbols, writes

    def test_linked_pte_geometry(self):
        symbols, writes = self.geometry_fixture()
        result = m.linked_geometry(symbols, writes)
        self.assertEqual(len(result['pairs']), 2)
        for old_slot in (1, 33):
            self.assertEqual(old_slot * 8 // 32, (old_slot + 1) * 8 // 32)

    def test_wrong_second_page_rejected(self):
        symbols, writes = self.geometry_fixture()
        writes[symbols['gcb_leaf'] + 4 * 8] = writes[symbols['gcb_leaf'] + 3 * 8]
        with self.assertRaises(ValueError):
            m.linked_geometry(symbols, writes)

    def test_unaligned_leaf_rejected(self):
        symbols, writes = self.geometry_fixture()
        symbols['gcb_leaf'] += 8
        with self.assertRaises(ValueError):
            m.linked_geometry(symbols, writes)

    def test_nonleaf_mapping_rejected(self):
        symbols, writes = self.geometry_fixture()
        writes[symbols['gcb_mid']] = 1
        with self.assertRaises(ValueError):
            m.linked_geometry(symbols, writes)

    def test_no_replay_claim_in_static_target_inventory(self):
        bitmap = json.loads((m.BASE / 'combined-bits.json').read_bytes())
        self.assertTrue(all(not r['native_exclusion_identity_claimed'] for r in m.targets(bitmap)))


if __name__ == '__main__':
    unittest.main()
