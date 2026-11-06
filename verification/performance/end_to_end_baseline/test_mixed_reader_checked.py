from pathlib import Path
import unittest

from run_mixed_reader_checked import fixture, check, BEFORE, AFTER
from test_mixed_reader import mixed_fixture


class SampledStallFixtureTests(unittest.TestCase):
    def test_requires_both_observations(self):
        text = mixed_fixture()+'\n'+BEFORE+'0\n'+AFTER+'\n'
        self.assertEqual(check(text)['ar_stalled_before_extra_edge'], 0)
        for wrong in (mixed_fixture(), text+'\n'+AFTER, text.replace('stalled=1','stalled=0')):
            with self.assertRaises(ValueError):
                check(wrong)

    def test_transform_retains_original_checks_and_inserts_a_sampling_edge(self):
        source = Path(__file__).with_name('qbs_mixed_reader_tb.sv').read_text()
        after = fixture(source)
        self.assertIn('@(posedge clk);\n        if (!av || ardy || ar.size != 5)', after)
        self.assertIn('Wide stalled AR lost across older narrow fault', after)
        self.assertIn('finish_fault(QBS_READ_FAULT_AXI_RESPONSE', after)
        self.assertEqual(after.count('MIXED_READER_AR_SAMPLED'), 1)
        with self.assertRaises(ValueError):
            fixture(after)


if __name__ == '__main__':
    unittest.main()
