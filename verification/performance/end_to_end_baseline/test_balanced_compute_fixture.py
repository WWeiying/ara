from pathlib import Path
import unittest

from balanced_compute_fixture import fixture


class BalancedFixture(unittest.TestCase):
    def test_inherited_checks_and_physical_observations(self):
        source=Path(__file__).with_name('qbs_wide_compute_tb.sv').read_text()
        for clone in (0,1):
            text,report=fixture(source,clone)
            for token in ('WC_GOLDEN_COUNTER_OR_FLAGS','WC_GOLDEN_OUTPUT','WC_RESULT_NOT_HELD',
                          'WC_OWNED_FOUR_ROW_WINDOW','BC_PHYSICAL episode=',
                          'bc_corrections+=$countones','bc_fp_slot++','bc_fp_acc++'):
                self.assertIn(token,text)
            self.assertIn('parameter bit Balanced = 0',text)
            self.assertNotIn('parameter bit Mixed',text)
            self.assertEqual('!`FP.mixed_found' in text,bool(clone))
            self.assertTrue(report['original_goldens_checks_retained'])
            if clone:
                self.assertIn('.BalancedMatrixDot(Balanced)',text)
                self.assertIn('read_case(fd,0);read_case(fd,1);',text)
                self.assertIn('kind<=7',text)
                self.assertIn('last_correction=%0d lanes=%0d integer_busy=%0d',text)
                self.assertIn('if(kind==5 || kind==6)',text)
                self.assertIn('MC_FAULT_PASS recovery=3 faults=3',text)
                self.assertNotIn('if(kind>=5)',text)

    def test_drift_fails_closed(self):
        for text in ('',Path(__file__).with_name('qbs_wide_compute_tb.sv').read_text()*2):
            with self.assertRaises(ValueError):fixture(text,True)


if __name__=='__main__':unittest.main()
