import unittest

from analyze_context_attribution import analyze

DECISION = ('GGML_RISCV_QBS_CONTEXT_LOOKAHEAD graph_epoch=2 current_index=3 '
            'examined_index=4 current=0x100 examined=0x200 source=0x300 source_data=0x1000 '
            'source_bytes=64 write_data=0x1020 write_bytes=64 op=ROPE '
            'reason=may_modify_activation decision=0\n')
LIFETIME = ('GGML_RISCV_QBS_LIFETIME graph_epoch=2 op_id=0x100 source_id=0x300 '
            'source_data=0x1000 weight=blk.0.attn_q.weight\n')


class AttributionAnalysisTest(unittest.TestCase):
    def test_join_future_record_and_overlap(self):
        result = analyze('Q8K_MODEL_BEGIN enabled=0\n' + DECISION + LIFETIME)
        self.assertEqual(result['joined_quantized_nodes'], 1)
        self.assertTrue(result['groups'][0]['range_overlap'])
        self.assertEqual(result['groups'][0]['weight'], 'blk.0.attn_q.weight')

    def test_mode_scope_and_touching_ranges(self):
        text = 'Q8K_MODEL_BEGIN enabled=0\n' + LIFETIME
        text += 'Q8K_MODEL_BEGIN enabled=1\n' + DECISION.replace('0x1020', '0x1040')
        result = analyze(text)
        self.assertEqual(result['unresolved_records'], 1)
        self.assertFalse(result['groups'][0]['range_overlap'])

    def test_reject_drift_unscoped_duplicate(self):
        for text in (DECISION,
                     'Q8K_MODEL_BEGIN enabled=0\n' + DECISION + LIFETIME.replace('0x300', '0x301'),
                     'Q8K_MODEL_BEGIN enabled=0\n' + DECISION + LIFETIME + LIFETIME):
            with self.assertRaises(ValueError):
                analyze(text)


if __name__ == '__main__':
    unittest.main()
