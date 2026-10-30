"""Source transformation guards; actual runtime validation is separate."""
import unittest
from prepare_native_candidate import SOURCE, transform


class CandidateTests(unittest.TestCase):
    def test_scoped_transform(self):
        source = SOURCE.read_text()
        result = transform(source)
        self.assertEqual(result.count('const int paired_heads ='),1)
        self.assertEqual(result.count('akv_pair_qk_f16_dispatch(paired_heads,'),1)
        self.assertEqual(result.count('akv_pair_pv_f16_dispatch(paired_heads,'),1)
        selection = result.index('const int paired_heads =')
        self.assertLess(selection,result.index('issue_full(&plan->descriptor, 0u)',selection))
        prefill = source.index('akv_attention_execute_v2_prefill_native(')
        self.assertEqual(source[prefill:],result[result.index('akv_attention_execute_v2_prefill_native('):])
        self.assertNotIn('bench_pair_enabled',result)

    def test_ambiguous_missing_or_reapplied_rejected(self):
        source = SOURCE.read_text()
        for text in (source+source,source.replace('qk_panel4_enabled_for_plan(plan);','0;'),
                     transform(source)):
            with self.assertRaises(ValueError):
                transform(text)


if __name__ == '__main__':
    unittest.main()
