"""Check selection roots against the complete historical701 report tree."""
import csv
import json
from pathlib import Path
import unittest

from report_scope_ancestors import report_ancestors

OUT = Path(__file__).resolve().parents[2] / 'verification/out'


class ActualReportAncestorTests(unittest.TestCase):
    def test_four_group_targets_have_only_selectable_ancestors(self):
        def load(relative):
            return json.loads((OUT / relative).read_bytes())
        qbs = load('qbs-rooted-report-701-20261006-01/config.json')
        debug = load('operand-debug-1832-application-full701-20261006-01/config.json')['native_config']
        ff1 = load('ff1-native904-capture-20261006-02/config.json')
        rebind = load('operand-native1144-rebound-701-parentcheck-20261006-01.json')
        targets = (set(qbs['plan']['scopes']) | set(debug['plan']['scopes']) |
                   set(ff1['plan']['scopes']) | {r['scope'] for r in rebind['records']})
        self.assertEqual(len(targets), 74)
        with (OUT / 'raw701-dve-20261006-01/summary.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        roots = report_ancestors(rows, targets)
        self.assertTrue(targets <= set(roots))
        self.assertEqual(len(roots), len(set(roots)))
        for lane in range(4):
            false_parent = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d]' % lane
            self.assertNotIn(false_parent, roots)
            self.assertIn(false_parent + '.i_lane', roots)
        self.assertIn('ara_tb.dut.i_ara_soc.i_system', roots)


if __name__ == '__main__':
    unittest.main()
