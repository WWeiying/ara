#!/usr/bin/env python3
import copy
import unittest
from run_shared_fma_compact import compare_reports


class AcceptanceGate(unittest.TestCase):
    def setUp(self):
        self.report = dict(state='PASS', paired_cases=1, pairs=[dict(case='test',
            baseline_finish=100, shared_finish=101, baseline_hw_cycles=['10'],
            shared_hw_cycles=['11'], baseline_micro=[['dot', '3', 'actual=1']],
            shared_micro=[['dot', '4', 'actual=1']])])

    def test_exact(self):
        self.assertEqual(compare_reports(self.report, copy.deepcopy(self.report))['state'], 'PASS')

    def test_reject_changes(self):
        for field in ('baseline_finish', 'shared_finish', 'baseline_hw_cycles',
                      'shared_hw_cycles', 'baseline_micro', 'shared_micro', 'case'):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.report)
                changed['pairs'][0][field] = 'changed'
                with self.assertRaises(ValueError):
                    compare_reports(self.report, changed)

    def test_reject_incomplete_or_failed(self):
        for field, value in (('state', 'FAIL'), ('paired_cases', 2), ('pairs', [])):
            changed = copy.deepcopy(self.report)
            changed[field] = value
            with self.assertRaises(ValueError):
                compare_reports(self.report, changed)


if __name__ == '__main__':
    unittest.main()
