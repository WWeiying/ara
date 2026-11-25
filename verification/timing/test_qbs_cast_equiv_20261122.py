import subprocess
import unittest

import run_qbs_cast_equiv_20261122 as check


class CastEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = subprocess.check_output(
            ['git', 'show', f'{check.BEFORE}:{check.REL}'], cwd=check.ROOT).decode()
        cls.after = (check.ROOT / check.REL).read_text()

    def test_real_scope(self):
        self.assertEqual(check.scope_body(self.before), check.scope_body(self.after))

    def test_state_change_rejected(self):
        changed = self.after.replace('cast_rr_q <=', 'schedule_rr_q <=')
        self.assertNotEqual(check.scope_body(self.before), check.scope_body(changed))

    def test_exact_port_extraction(self):
        for source, name in [(self.before, 'cast_before'), (self.after, 'cast_after')]:
            start = source.index('  if (SplitIssue) begin : gen_cast_port')
            stop = source.index('  if (HalfScaleIssue)', start)
            self.assertIn(source[start:stop], check.cast_wrapper(source, name))

    def test_rename_only_module_identity(self):
        renamed = check.rename_module(self.before.encode(), b'_before')
        self.assertEqual(renamed.replace(b'qbs_fp_accumulator_before', b'qbs_fp_accumulator'),
                         self.before.encode())

    def test_anchor_drift_rejected(self):
        with self.assertRaises(ValueError):
            check.one_replace('duplicate duplicate', 'duplicate', 'new')

    def test_six_real_instances_and_coverage_gates(self):
        base = (check.ROOT / 'verification/qbs/qbs_fp_split_tb.sv').read_text()
        generated = check.make_tb(base)
        self.assertEqual(generated.count('qbs_fp_accumulator_before #('), 3)
        self.assertEqual(generated.count('qbs_fp_accumulator_after #('), 3)
        self.assertNotIn('gen_dut[', generated)
        self.assertIn('assert (direct_done)', generated)
        self.assertIn('Missing dual-return flag stress', generated)
        self.assertIn('Missing live reset test', generated)
        self.assertEqual(generated.count('Accumulator cycle/control mismatch'), 3)


if __name__ == '__main__':
    unittest.main()
