import unittest
from unittest.mock import patch

from run_layout_model_pair import check


def log():
    rows = ['DECODE_LAYOUT_DISPATCH original=600 candidate=0',
            'DECODE_LAYOUT_DISPATCH original=0 candidate=600']
    rows += [f'Q8K_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
             for k in range(2) for s in range(3)]
    rows += ['Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured', 'GUEST_TEST_EXIT=0']
    return '\n'.join(rows)


class PairTest(unittest.TestCase):
    @patch('run_layout_model_pair.native_accounting', return_value={})
    def test_dispatch_and_complete_comparisons(self, accounting):
        result = check(log())
        self.assertEqual(result['logits_compared'], 911616)
        accounting.assert_called_once()

    @patch('run_layout_model_pair.native_accounting', return_value={})
    def test_reject_identical_candidate_both_sides(self, _):
        with self.assertRaises(ValueError):
            check(log().replace('original=600 candidate=0', 'original=0 candidate=600'))

    @patch('run_layout_model_pair.native_accounting', return_value={})
    def test_reject_incomplete_mismatch_and_workload_drift(self, _):
        for text in (log().replace('kind=1 step=2', 'kind=1 step=1'),
                     log().replace('bitwise=1', 'bitwise=0', 1),
                     log().replace('candidate=600', 'candidate=601'),
                     log().replace('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1')):
            with self.assertRaises(ValueError):
                check(text)


if __name__ == '__main__':
    unittest.main()
