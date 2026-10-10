import copy
import json
from pathlib import Path
import unittest

import lzc_selector_native_successor as successor


class SuccessorTests(unittest.TestCase):
    def setUp(self):
        self.old = Path('/old/prepared')
        self.new = Path('/new/prepared')
        self.plan = json.loads((successor.ORIGINAL / 'experiments.json').read_bytes())
        for row in self.plan['experiments']:
            row['cwd'] = row['cwd'].replace(str(successor.ORIGINAL), str(self.old))
            for field in ('compile_argv', 'run_argv'):
                row[field] = [a.replace(str(successor.ORIGINAL), str(self.old)) for a in row[field]]
        self.fresh = successor.successor_plan(self.plan, self.old, self.new)

    def test_only_default_timing_changes_for_all_eight_cases(self):
        before = copy.deepcopy(self.plan)
        successor.validate_successor(self.plan, self.fresh, self.old, self.new)
        self.assertEqual(self.plan, before)
        for old, new in zip(self.plan['experiments'], self.fresh['experiments']):
            self.assertEqual((old['width'], old['selector'], old['parity']),
                             (new['width'], new['selector'], new['parity']))
            self.assertEqual(new['compile_argv'].count(successor.TIMING), 1)

    def test_parameter_or_input_changes_rejected(self):
        for field in ('width', 'selector', 'parity', 'top'):
            fresh = copy.deepcopy(self.fresh)
            fresh['experiments'][0][field] = 'changed'
            with self.assertRaises(ValueError):
                successor.validate_successor(self.plan, fresh, self.old, self.new)

    def test_any_other_compile_or_runtime_option_rejected(self):
        for field in ('compile_argv', 'run_argv'):
            fresh = copy.deepcopy(self.fresh)
            fresh['experiments'][0][field].append('+change')
            with self.assertRaises(ValueError):
                successor.validate_successor(self.plan, fresh, self.old, self.new)

    def test_missing_duplicate_or_wrong_timing_rejected(self):
        for replacement in ([], [successor.TIMING, successor.TIMING], ['-timescale=1ps/1ps']):
            fresh = copy.deepcopy(self.fresh)
            row = fresh['experiments'][0]
            row['compile_argv'].remove(successor.TIMING)
            row['compile_argv'].extend(replacement)
            with self.assertRaises(ValueError):
                successor.validate_successor(self.plan, fresh, self.old, self.new)
        with self.assertRaises(ValueError):
            successor.validate_successor(self.plan, {'experiments': self.fresh['experiments'][:7]},
                                         self.old, self.new)


if __name__ == '__main__':
    unittest.main()
