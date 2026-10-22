import inspect
import unittest

import classify_qbs_all_hits780 as q


class ExpansionTests(unittest.TestCase):
    def test_exact_filter_transform(self):
        source = inspect.getsource(q.p.report)
        expanded = q.expanded_function(source)
        self.assertIn('source_proof', expanded.__code__.co_names)
        self.assertIn('identity', expanded.__code__.co_names)
        self.assertIn('excluded_bits', str(expanded.__code__.co_consts))

    def test_missing_or_altered_filter_rejected(self):
        source = inspect.getsource(q.p.report)
        for value in (source.replace('bank != 0', 'bank != 1'),
                      source.replace('gen_bank_row[0]', 'gen_bank_row[1]')):
            with self.assertRaises(ValueError): q.expanded_function(value)

    def test_pending_not_approved_and_preserved_HOLD(self):
        scope = 'bank0'
        name = 'gen_write_merge[1].gen_bank_plane[2].gen_bank_row[0].gen_byte_merge[1].hit'
        records = [dict(scope=scope, signal=name, bit=2, raw_coordinates=[2, 3],
                        classification='SOURCE_MAPPING_ZERO_NATIVE_REQUIRED'),
                   dict(scope=scope, signal=name, bit=6, raw_coordinates=[6, 7],
                        classification='SOURCE_MAPPING_ZERO_NATIVE_REQUIRED'),
                   dict(scope=scope, signal=name, bit=9, raw_coordinates=[9],
                        classification='MAPPING_WITNESS_ARBITRATION_HOLD')]
        s = q.summarize(records, {(scope, name, 2)})
        self.assertEqual(s['residual_directions_by_class'], dict(
            PENDING128_NOT_YET_QUALIFIED=2, NEW_MAPPING_ZERO_NATIVE_REQUIRED=2,
            MAPPING_WITNESS_ARBITRATION_HOLD=1))
        self.assertEqual(len(s['mapping_HOLD_examples']), 1)

    def test_all_side_main_mapping_covers_old_even_domain_subset(self):
        for bank in (0, 1):
            tight, _ = q.p.finite(bank)
            even, _ = q.p.even.even_possible(bank)
            self.assertLessEqual(tight, even)
            self.assertTrue(any(key[2] == 2 for key in tight))
            self.assertTrue(any(key[0] == 'weight' for key in tight))

    def test_both_context_banks_remain_reachable(self):
        for bank in (0, 1):
            keys, _ = q.p.finite(bank)
            for row in range(4):
                self.assertTrue(any(k[0] == 'activation' and k[1] == row for k in keys))


if __name__ == '__main__': unittest.main()
