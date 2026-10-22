import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import reviewed_wall_budgets as budgets


class WallBudgetTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(budgets.POLICY.read_text())
        self.cases = [dict(source_name=r['source_name'], kind='directed',
                           elf_sha256=r['elf_sha256'], timeout_s=300,
                           oracle='selfcheck+trace-audit', watchdog_cycles=12345)
                      for r in self.policy['cases']]
        self.evidence = {}
        for r in self.policy['cases']:
            self.evidence[r['history_outcome']] = dict(status='PASS', elf_sha256=r['elf_sha256'])
            self.evidence[r['history_summary']] = [dict(status='PASS', name=r['source_name'],
                                                        elapsed_s=r['historical_elapsed_s'])]
            self.evidence[r['history_audit']] = dict(status='PASS', errors=[])

    def read(self, path):
        return copy.deepcopy(self.policy if Path(path) == budgets.POLICY else self.evidence[str(path)])

    def apply(self):
        with patch.object(budgets.base, 'read', side_effect=self.read), patch.object(budgets.base, 'pins', return_value={}):
            return budgets.apply(self.cases)[0]

    def test_all_budgets_and_semantics(self):
        result = self.apply()
        self.assertEqual([c['timeout_s'] for c in result], [1200] * 12 + [2400, 7200])
        self.assertTrue(all(c['timeout_s'] == 300 for c in self.cases))
        for before, after in zip(self.cases, result):
            for key in ('oracle', 'watchdog_cycles', 'elf_sha256', 'kind'):
                self.assertEqual(before[key], after[key])

    def test_changed_elf_rejected(self):
        self.cases[0]['elf_sha256'] = 'different'
        with self.assertRaises(ValueError):
            self.apply()

    def test_missing_case_rejected(self):
        self.cases.pop()
        with self.assertRaises(ValueError):
            self.apply()

    def test_budget_change_rejected(self):
        self.policy['cases'][0]['wall_seconds'] = 7200
        with self.assertRaises(ValueError):
            self.apply()

    def test_failed_evidence_rejected(self):
        self.evidence[self.policy['cases'][0]['history_audit']]['status'] = 'FAIL'
        with self.assertRaises(ValueError):
            self.apply()

    def test_existing_larger_budget_preserved(self):
        self.cases[0]['timeout_s'] = 1500
        self.assertEqual(self.apply()[0]['timeout_s'], 1500)

    def test_duplicate_case_rejected(self):
        self.cases.append(copy.deepcopy(self.cases[0]))
        with self.assertRaises(ValueError):
            self.apply()


if __name__ == '__main__':
    unittest.main()
