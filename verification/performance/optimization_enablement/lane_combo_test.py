"""Small fail-closed tests; inherited oracles/checkers are not weakened."""
import unittest
import lane_combo_run as gate


class ComboTests(unittest.TestCase):
    def test_exact_bench_change(self):
        for path in (gate.ROOT/gate.QK_REL/'fpu_gate_tb.sv',
                     (gate.ROOT/gate.FP_REL).with_name('vmfpu_fp_tb.sv')):
            old = path.read_text()
            new = gate.adapt(old)
            self.assertEqual(new.replace('.SharedFma(ara_pkg::EnableSharedFma)',
                                         ".SharedFma(1'b0)"), old)
            self.assertNotEqual(old, new)
        for invalid in ('', ".SharedFma(1'b0) .SharedFma(1'b0)"):
            with self.assertRaises(ValueError):
                gate.adapt(invalid)

    def test_probe_configuration_and_work(self):
        text = ('LANE_COMBO_CONFIG shared_fma=1 shared_mul=1 resident=1 borrower=1 fma_latency=5\n'
                'LANE_COMBO_WORK fp16=2 fp32=0 private_returns=2 borrowed=24 returned=24 native=5\n')
        self.assertEqual(gate.probe_check(text, 'fullfp', {})['borrowed'], 24)
        for bad in (text + text, text.replace('shared_fma=1', 'shared_fma=0'),
                    text.replace('returned=24', 'returned=23'),
                    text.replace('fp16=2', 'fp16=0'), text.replace('fma_latency=5', 'fma_latency=3')):
            with self.assertRaises(ValueError):
                gate.probe_check(bad, 'fullfp', {})

    def test_qk_probe_matches_case_ledger(self):
        checked = dict(cases=[dict(mode=0, issued=10, returned=10),
                              dict(mode=1, issued=20, returned=18)])
        text = ('LANE_COMBO_CONFIG shared_fma=1 shared_mul=1 resident=1 borrower=1 fma_latency=5\n'
                'LANE_COMBO_WORK fp16=10 fp32=20 private_returns=28 borrowed=25 returned=25 native=0\n')
        gate.probe_check(text, 'qk', checked)
        with self.assertRaises(ValueError):
            gate.probe_check(text.replace('fp32=20', 'fp32=0'), 'qk', checked)


if __name__ == '__main__':
    unittest.main()
