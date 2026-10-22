import unittest

import prove_qbs_hit_congruence780 as p


class CongruenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = [p.finite(bank)[0] for bank in (0, 1)]

    def test_activation_closed_form_all_rows_banks(self):
        for keys in self.tables:
            for row in range(4):
                for lane in range(32):
                    for b in range(16):
                        self.assertEqual(('activation', row, 0, lane, b) in keys,
                                         p.activation_main_possible(row, lane, b))

    def test_all_nine_weight_profiles_union_parity(self):
        for keys in self.tables:
            for row in range(4):
                for lane in range(16):
                    for b in range(16):
                        self.assertEqual(('weight', row, 0, lane, b) in keys, lane % 2 == b % 2)

    def test_bad_interleaved_two_alignment_breaks_invariant(self):
        weak = p.finite(0, interleaved_step=2)[0]
        self.assertIn(('activation', 0, 0, 1, 2), weak)
        self.assertNotIn(('activation', 0, 0, 1, 2), self.tables[0])

    def test_row_only_parity_is_unsound(self):
        self.assertIn(('activation', 0, 0, 1, 0), self.tables[0])
        ctx, off = p.m.activation_target(20, 4, 4, 256)
        self.assertEqual((ctx, off - 4), (0, 1))

    def test_m8_cross_bank_context(self):
        ctx, off = p.m.activation_target(44, 8, 4, 256)
        self.assertEqual((ctx, off - 4), (4, 1))
        self.assertIn(('activation', 0, 0, 1, 0), self.tables[1])

    def test_pending_recompact_would_break_proof(self):
        legal = ('activation', 0, 0, 1, 0)
        illegal = ('activation', 0, 0, 1, 2)
        self.assertIn(legal, self.tables[0])
        self.assertNotIn(illegal, self.tables[0])

    def test_burst_and_page_four_alignment(self):
        for address in (0, 4, 12, 4092, 4096):
            for size in (136, 272, 1168, 2336):
                self.assertTrue(all(o % 4 == f % 4 == take % 4 == 0
                                    for o, f, take in p.even.compact_range(address, size)))

    def test_illegal_domain_rejected(self):
        with self.assertRaises(ValueError):
            p.finite(2)
        with self.assertRaises(ValueError):
            p.finite(0, interleaved_step=1)

    def test_actual_compact_witnesses_subset(self):
        for key, witness in p.legal_activation_beats().items():
            self.assertIn(key, self.tables[0])
            self.assertLess(witness['writer'], witness['take'])
            self.assertEqual(witness['base'] % 4, 0)

    def test_overapprox_start_is_not_a_legal_read_claim(self):
        # ROW Q8K cannot produce offset30; its aligned block stride is mod4=0.
        key = ('activation', 0, 0, 0, 6)
        self.assertIn(key, self.tables[0])
        self.assertNotIn(key, p.legal_activation_beats())


if __name__ == '__main__':
    unittest.main()
