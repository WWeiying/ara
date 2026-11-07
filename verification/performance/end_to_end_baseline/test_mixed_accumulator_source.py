from pathlib import Path
import unittest

from mixed_accumulator_source import accumulator, compute
from mixed_compute_fixture import fixture

ROOT=Path('/home/wangwy/openproject/ara_dsa')


class MixedSource(unittest.TestCase):
    def test_exact_reversible_production_sources_and_fallback(self):
        text,report=accumulator((ROOT/'hardware/src/vlsu/qbs/qbs_fp_accumulator.sv').read_text())
        self.assertTrue(report['source_reversible'])
        self.assertTrue(report['default_disabled'])
        self.assertIn('!is_half_scale && !use_mixed',text)
        self.assertIn('mixed_accumulator_index[2:0]',text)
        self.assertNotIn('entry_inflight_q[mixed_index] <= 1\'b0',text)
        self.assertIn('(mixed_out_valid ? mixed_flags',text)
        body,notes=compute((ROOT/'hardware/src/vlsu/qbs/qbs_compute_engine.sv').read_text())
        self.assertTrue(notes['source_reversible'])
        self.assertIn('.MixedScaleIssue(MixedScaleIssue)',body)

    def test_missing_or_drifted_source_rejected(self):
        for transform,path in ((accumulator,'qbs_fp_accumulator.sv'),(compute,'qbs_compute_engine.sv')):
            original=(ROOT/'hardware/src/vlsu/qbs'/path).read_text()
            for bad in ('',original+'\n',original+original):
                with self.assertRaises(ValueError):transform(bad)

    def test_fixture_preserves_existing_checks_in_both_modes(self):
        source=(ROOT/'verification/performance/end_to_end_baseline/qbs_wide_compute_tb.sv').read_text()
        for clone in (False,True):
            text,notes=fixture(source,clone)
            self.assertTrue(notes['source_reversible'])
            self.assertIn('WC_GOLDEN_COUNTER_OR_FLAGS',text)
            self.assertIn('WC_OWNED_FOUR_ROW_WINDOW',text)
            self.assertIn('WC_MISSING_CAMPAIGN_COVERAGE',text)
            self.assertIn('MC_TIME episode=',text)
            self.assertEqual('MC_FAULT_TRIGGER' in text,clone)
            self.assertEqual('FP.mixed_fire' in text,clone)
        for bad in ('',source+source):
            with self.assertRaises(ValueError):fixture(bad,True)


if __name__=='__main__':unittest.main()
