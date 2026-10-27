import unittest
from unittest.mock import patch

from run_float_gap_pair import check


def log():
    return '\n'.join([
        'Q8K_MODEL_BEGIN enabled=0',
        'GGML_RISCV_QBS_EXEC type=Q4_K context_fill=10 context_release=10 context_reuse=20',
        'Q8K_MODEL_BEGIN enabled=1',
        'GGML_RISCV_QBS_EXEC type=Q4_K context_fill=8 context_release=8 context_reuse=24',
        *[f'Q8K_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
          for k in range(2) for s in range(3)],
        'Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured', 'GUEST_TEST_EXIT=0'])


ACTIVITY = {'0': {'totals': {'quantizations': 10, 'cross_op_quantization_skips': 2}},
            '1': {'totals': {'quantizations': 8, 'cross_op_quantization_skips': 4}}}


class FloatPairTest(unittest.TestCase):
    @patch('run_float_gap_pair.analyze', return_value=ACTIVITY)
    @patch('run_float_gap_pair.native_accounting', return_value={})
    def test_context_deltas_do_not_hide_work(self, native, _):
        result = check(log())
        self.assertEqual(result['quantizations_saved'], 2)
        self.assertEqual(result['context_counts'][1]['context_fill'], 8)
        normalized = native.call_args.args[0]
        self.assertIn('context_fill=0 context_release=0 context_reuse=0', normalized)

    @patch('run_float_gap_pair.analyze', return_value=ACTIVITY)
    @patch('run_float_gap_pair.native_accounting', return_value={})
    def test_reject_leak_and_numerical_failure(self, _, __):
        for text in (log().replace('context_release=8','context_release=7'),
                     log().replace('bitwise=1','bitwise=0',1)):
            with self.assertRaises(ValueError): check(text)

    @patch('run_float_gap_pair.analyze', return_value={'0': ACTIVITY['0'], '1': ACTIVITY['0']})
    def test_reject_ineffective_toggle(self, _):
        with self.assertRaises(ValueError): check(log())


if __name__ == '__main__': unittest.main()
