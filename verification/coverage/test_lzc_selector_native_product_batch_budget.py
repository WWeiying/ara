"""Timing-only workload budgeting; no DVE launch in tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import lzc_selector_native_product_batch_budget as budget


class BudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = budget.batch.product.OUT / 'lzc_selector_native_product_batch-707-20261006-01'
        cls.old = json.loads((cls.previous / 'batch-plan.json').read_bytes())

    def test_exact_workload_and_conservative_proxy(self):
        result = budget.estimate(self.old, 277.34)
        self.assertEqual(result['total_state_checks'], 94080)
        self.assertEqual(result['local_five_stage_state_checks'], 85680)
        self.assertEqual(result['global_before_final_state_checks'], 8400)
        self.assertEqual(result['maximum_branch_parent_cell_queries'], 7344)
        self.assertEqual(sum(result['maximum_transaction_counts'].values()), 1203)
        self.assertEqual(result['estimated_with_margin_seconds'], 10223)
        self.assertLessEqual(result['estimated_with_margin_seconds'], budget.DVE_SECONDS)
        self.assertLess(budget.WATCHDOG_SECONDS, 3 * 3600)
        self.assertFalse(result['reload_on_timeout'])

    def test_nonpositive_or_over_cap_timing_rejected(self):
        for seconds in (0, -1, 400):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                budget.estimate(self.old, seconds)

    def test_prepare_preserves120targets_script_and_allprotection(self):
        with tempfile.TemporaryDirectory(dir=budget.batch.product.OUT, prefix='lzc_selector_native_budget_unit-') as temp:
            output = Path(temp)
            output.rmdir()

            def original_prepare(source, discovery, destination):
                destination.mkdir()
                budget.batch.write(destination / 'selection.tcl', 'set test_fixture 1\n')
                plan = json.loads(json.dumps(self.old))
                plan['environment']['LZC_SELECTOR_NATIVE_BATCH_SELECTION'] = str(destination / 'selection.tcl')
                budget.batch.write(destination / 'batch-plan.json', plan)
                budget.batch.write(destination / 'batch-plan.sha256.json', {
                    str(destination / 'batch-plan.json'): budget.sha(destination / 'batch-plan.json')})

            with mock.patch.object(budget.batch, 'prepare', side_effect=original_prepare), \
                 mock.patch.object(budget.subprocess, 'Popen') as launch:
                budget.prepare(self.previous, output)
                launch.assert_not_called()
            revised = json.loads((output / 'batch-plan.json').read_bytes())
            self.assertEqual(revised['targets'], self.old['targets'])
            self.assertEqual(revised['protection_rows'], self.old['protection_rows'])
            self.assertEqual([i for i, (a, b) in enumerate(zip(self.old['command'], revised['command'])) if a != b], [2])
            self.assertEqual(revised['command'][2], '10500s')
            self.assertEqual(revised['command'][-1], str(budget.batch.SCRIPT))
            self.assertEqual(revised['timing_successor']['immutable_script_sha256'], budget.sha(budget.batch.SCRIPT))
            budget.batch.product.check_pins(json.loads((output / 'batch-plan.sha256.json').read_bytes()))
            self.assertEqual(budget.batch.SCRIPT.read_text().count('gui_open_cov '), 1)

    def test_nontiming_candidate_change_rejected(self):
        with tempfile.TemporaryDirectory(dir=budget.batch.product.OUT, prefix='lzc_selector_native_budget_unit-') as temp:
            output = Path(temp)
            output.rmdir()

            def bad_prepare(source, discovery, destination):
                destination.mkdir()
                budget.batch.write(destination / 'selection.tcl', 'set test_fixture 1\n')
                plan = json.loads(json.dumps(self.old))
                plan['targets'][0]['candidate']['parameters']['MODE'] = 0
                budget.batch.write(destination / 'batch-plan.json', plan)

            with mock.patch.object(budget.batch, 'prepare', side_effect=bad_prepare), self.assertRaises(ValueError):
                budget.prepare(self.previous, output)

    def test_budget_math_never_spawns_tools(self):
        with mock.patch.object(budget.subprocess, 'Popen') as launch:
            budget.estimate(self.old, 277.34)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
