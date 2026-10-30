#!/usr/bin/env python3
"""Source composition checks only; do not claim native runtime acceptance."""
import unittest
import build_combined_candidate as c
from pre_promotion_fixture import source


class CombinedTests(unittest.TestCase):
    def test_preserves_production_entries_and_both_optins(self):
        original = source()
        value = c.transform(original)
        self.assertEqual(value.count('const int paired_heads ='),1)
        self.assertEqual(value.count('const int paired_pv ='),1)
        for call in ('akv_pair_qk_f16_dispatch(paired_heads,',
                     'akv_pair_pv_f16_dispatch(paired_heads,',
                     'akv_prefill_pair_pv_dispatch(paired_pv,'):
            self.assertEqual(value.count(call),1)
        for name in ('akv_attention_execute_v2_native',
                     'akv_attention_execute_v2_with_features_native',
                     'akv_attention_execute_v2_prefill_native'):
            self.assertEqual(value.count(name),original.count(name))
        self.assertNotIn('bench_pair_enabled',value)
        self.assertNotIn('bench_active',value)

    def test_source_drift_and_double_application_fail_closed(self):
        original = source()
        with self.assertRaises(ValueError):
            c.transform(original.replace('const int qk_panel4 =','const int changed =',1))
        with self.assertRaises(ValueError):
            c.transform(c.transform(original))

    def test_promoted_source_is_exact_composed_candidate(self):
        self.assertEqual(c.SOURCE.read_text(),c.transform(source()))


if __name__ == '__main__':
    unittest.main()
