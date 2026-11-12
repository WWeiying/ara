from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import soc_campaign as c


class CampaignTests(unittest.TestCase):
    def test_minimal_finite_queue(self):
        self.assertEqual(len(c.RUNS), 7)
        self.assertEqual(c.RUNS[-1], ('baseline', 'resident_sdk'))
        self.assertEqual(sum(name == 'qbs_m8' for arm, name in c.RUNS), 1)

    def test_no_blanket_no_regression_claim(self):
        rows = c.compare_cycles([100, 200, 300], [101, 190, 300])
        self.assertEqual([r['cycle_delta'] for r in rows], [1, -10, 0])
        self.assertEqual([r['regression'] for r in rows], [True, False, False])
        for a in ([], [1, 2], [1, 2, 0], [1.0, 2, 3]):
            with self.assertRaises(ValueError): c.compare_cycles(a, [1, 2, 3])

    def test_success_never_accepts_error(self):
        c.successful('Core Test *** SUCCESS ***\nUVM_ERROR : 0\n')
        for bad in ('', 'Core Test *** SUCCESS ***\nFatal: bad',
                    'Core Test *** SUCCESS ***\nUVM_ERROR : 1',
                    'Core Test *** SUCCESS ***\nCore Test *** SUCCESS ***'):
            with self.assertRaises(ValueError): c.successful(bad)

    def test_four_lane_selection_and_drain(self):
        text = '\n'.join('FMA_SOC_SUMMARY lane%d shared=1 cycles=9 issued=2 retired=2 blocked=0 latency_wait=0 fma=0,1,0,0' % i for i in range(4))
        self.assertEqual(len(c.fma_summary(text, 1, True)), 4)
        for bad in (text.replace('retired=2', 'retired=1'), text.replace('shared=1', 'shared=0'),
                    text.replace('issued=2 retired=2', 'issued=0 retired=0')):
            with self.assertRaises(ValueError): c.fma_summary(bad, 1, True)

    def test_already_completed_build_wait_does_not_launch(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); (p/'build.json').write_text('{}')
            with patch.object(c.os, 'read', side_effect=AssertionError('must not wait')):
                c.wait_builds([p], 1)


if __name__ == '__main__': unittest.main()
