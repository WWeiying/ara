"""Only completed checked runs with the right linked decoder comparison pass."""
from pathlib import Path
import unittest
from unittest.mock import patch
import audit_common_attention as a


class CommonAuditTest(unittest.TestCase):
    def test_nonterminal_or_unchecked_never_reads_build(self):
        status = dict(state='PASS', child_pid=None)
        result = dict(state='PASS', simulator_exit_code=0, post_pins_match=True, independent_protocol_checked=True)
        for target, key, value in [('status', 'state', 'RUNNING'), ('status', 'child_pid', 123),
                                   ('result', 'state', 'FAIL'), ('result', 'simulator_exit_code', 1),
                                   ('result', 'simulator_exit_code', False),
                                   ('result', 'post_pins_match', False), ('result', 'independent_protocol_checked', False)]:
            first, second = dict(status), dict(result)
            (first if target == 'status' else second)[key] = value
            with self.subTest(target=target, key=key), \
                    patch.object(a.s, 'read_json', side_effect=[first, second]), \
                    patch.object(a, 'checked_build') as build:
                with self.assertRaises(ValueError): a.checked_run(Path('/unused'))
                build.assert_not_called()

    def test_linked_implementations_must_match(self):
        scalar = '<dequantize_row_q8_0>:\n 100: 12345678 fcvt.s.w\n 104: 12345678 fmul.s\n 108: 12345678 fsw\n\n'
        vector = '\n 200: 12345678 vle8.v\n 204: 12345678 vsext.vf4\n 208: 12345678 vfcvt.f.x.v\n 20c: 12345678 vfmul.vf\n 210: 12345678 vse32.v\n\n'
        variants = [({}, scalar),
                    (dict(rvv_value_decode=True, ordinary_value_decode='unchanged production scalar decoder'),
                     scalar + '<value_rvv_decode>:' + vector),
                    (dict(rvv_value_decode=True, rvv_baseline_decode=True,
                          ordinary_value_decode='same RVV decoder as candidate'), '<fair_value_decode>:' + vector)]
        for report, symbols in variants:
            self.assertIsInstance(a.checked_decoder_comparison(report, symbols), dict)
            for wrong in ('', '<unused>:', '<dequantize_row_q8_0>:\n<value_rvv_decode>:\n<fair_value_decode>:'):
                with self.subTest(report=report, wrong=wrong), self.assertRaises(ValueError):
                    a.checked_decoder_comparison(report, wrong)

    def test_symbol_name_alone_does_not_prove_scalar_or_vector(self):
        with self.assertRaises(ValueError):
            a.checked_decoder_comparison({}, '<dequantize_row_q8_0>:')
        report = dict(rvv_value_decode=True, rvv_baseline_decode=True,
                      ordinary_value_decode='same RVV decoder as candidate')
        with self.assertRaises(ValueError):
            a.checked_decoder_comparison(report, '<fair_value_decode>:\n 200: 12345678 fmul.s\n')


if __name__ == '__main__': unittest.main()
