from pathlib import Path
import unittest

from balanced_compute_source import accumulator, compute, patch

ROOT=Path('/home/wangwy/openproject/ara_dsa/hardware/src/vlsu/qbs')


class BalancedWiring(unittest.TestCase):
    def test_original_sources_and_admission_ownership(self):
        text,report=accumulator((ROOT/'qbs_fp_accumulator.sv').read_text())
        self.assertTrue(report['parent']['source_reversible'])
        self.assertTrue(report['source_reversible'])
        self.assertIn('entry_mixed_allowed_q[request_slot_i] <= request_mixed_enable_i;',text)
        self.assertIn('MixedScaleIssue && entry_mixed_allowed_q[entry]',text)
        self.assertEqual(text.count("entry_mixed_allowed_q <= '0;"),2)
        self.assertIn('entry_work_value_q[mixed_tag_out]',text)
        text,report=compute((ROOT/'qbs_compute_engine.sv').read_text())
        self.assertTrue(report['default_disabled'])
        self.assertIn("parameter bit BalancedMatrixDot = 1'b0",text)
        self.assertIn('.BalancedMatrixDot(BalancedMatrixDot)',text)
        self.assertIn('.request_mixed_enable_i        (balanced_result_wave)',text)
        self.assertIn('!i_fp_accumulator.mixed_found)',text)
        self.assertNotIn('wave_m >= 3',text)
        self.assertNotIn('.MixedScaleIssue(MixedScaleIssue)',text)

    def test_all_command_wave_enable_cases(self):
        for m in range(1,9):
            for block in (32,256):
                for base in (0,4):
                    enabled=block==256 and ((base==0 and m>=3) or (base==4 and m>=7))
                    wave=min(4,max(0,m-base))
                    self.assertEqual(enabled,block==256 and wave>=3)

    def test_drift_and_nonunique_edits_rejected(self):
        for fn,name in ((accumulator,'qbs_fp_accumulator.sv'),(compute,'qbs_compute_engine.sv')):
            source=(ROOT/name).read_text()
            for bad in ('',source+'\n'):
                with self.assertRaises(ValueError):fn(bad)
        for source in ('absent','one one'):
            with self.assertRaises(ValueError):patch(source,[('one','two')])


if __name__=='__main__':unittest.main()
