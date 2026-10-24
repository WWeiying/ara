"""Scope guards for candidate generation, not native acceptance."""
import unittest
from prepare_prefill_candidate import SOURCE, transform


class CandidateTests(unittest.TestCase):
    def test_scope_and_order(self):
        source = SOURCE.read_text()
        result = transform(source)
        original_decode = source.split('akv_status_t akv_attention_execute_v2_prefill_native(',1)[0]
        candidate_decode = result.split('akv_status_t akv_attention_execute_v2_prefill_native(',1)[0]
        self.assertEqual(candidate_decode.replace(
            '#include "../experimental/paired_heads/f32_pv/runtime.h"\n',''),original_decode)
        selection = result.index('const int paired_pv =')
        self.assertLess(selection,result.index('issue_full(',selection))
        self.assertEqual(result.count('akv_prefill_pair_pv_dispatch(paired_pv,'),1)
        self.assertEqual(source.count('akv_v2_update_outputs_f32_d128_gqa6('),
                         result.count('akv_v2_update_outputs_f32_d128_gqa6('))

    def test_drift_and_reapply_rejected(self):
        source = SOURCE.read_text()
        for bad in (source+source,transform(source),source.replace(
            'q_rows = problem->query_heads / problem->kv_heads;','q_rows = 1;')):
            with self.assertRaises(ValueError):
                transform(bad)


if __name__ == '__main__':
    unittest.main()
