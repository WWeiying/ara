import copy
import unittest
from audit_real_runtime import compare_performance, compare_commands, compare_runtime


class RuntimePerformanceAuditTests(unittest.TestCase):
    def setUp(self):
        self.old = dict(trials=[dict(trial=i, paired=i % 2, cycles=100+i,
                                    checksum='1234', fcsr=1, vcsr=5,
                                    hardware_totals=dict(busy_cycles=50)) for i in range(4)])

    def test_exact(self):
        result = compare_performance(self.old, copy.deepcopy(self.old))
        self.assertTrue(result['resource_regression_gate_pass'])
        self.assertTrue(result['complete_operator_performance_accepted'])

    def test_one_slow_call_not_hidden_by_faster_total(self):
        new = copy.deepcopy(self.old)
        new['trials'][0]['cycles'] += 1
        new['trials'][1]['cycles'] -= 20
        result = compare_performance(self.old, new)
        self.assertFalse(result['resource_regression_gate_pass'])
        self.assertFalse(result['complete_call_no_regression'])

    def test_absent_cycles_not_operator_performance(self):
        old = copy.deepcopy(self.old)
        for row in old['trials']:
            del row['cycles']
        result = compare_performance(old, copy.deepcopy(old))
        self.assertTrue(result['resource_regression_gate_pass'])
        self.assertIsNone(result['complete_call_no_regression'])
        self.assertFalse(result['complete_operator_performance_accepted'])

    def test_changed_counters_require_review(self):
        new = copy.deepcopy(self.old)
        new['trials'][0]['hardware_totals']['busy_cycles'] += 1
        result = compare_performance(self.old, new)
        self.assertFalse(result['resource_regression_gate_pass'])
        self.assertFalse(result['complete_operator_performance_accepted'])

    def test_performance_acceptance_requires_exact_command_ledger(self):
        old = [dict(seq=1, busy_cycles=10), dict(seq=2, busy_cycles=20)]
        new = [dict(seq=1, busy_cycles=11), dict(seq=2, busy_cycles=19)]
        result = compare_runtime(self.old, copy.deepcopy(self.old), old, new)
        self.assertTrue(result['complete_call_no_regression'])
        self.assertFalse(result['resource_regression_gate_pass'])
        self.assertFalse(result['complete_operator_performance_accepted'])

    def test_bad_output_rejected(self):
        new = copy.deepcopy(self.old)
        new['trials'][0]['checksum'] = 'bad'
        with self.assertRaises(ValueError):
            compare_performance(self.old, new)

    def test_invalid_cycle_values_rejected(self):
        for value in (0, -1, True, '100'):
            new = copy.deepcopy(self.old)
            new['trials'][0]['cycles'] = value
            with self.assertRaises(ValueError):
                compare_performance(self.old, new)

    def test_missing_call_rejected(self):
        new = copy.deepcopy(self.old)
        new['trials'].pop()
        with self.assertRaises(ValueError):
            compare_performance(self.old, new)

    def test_cycle_schema_asymmetry_rejected(self):
        new = copy.deepcopy(self.old)
        del new['trials'][0]['cycles']
        with self.assertRaises(ValueError):
            compare_performance(self.old, new)

    def test_offsetting_command_changes_not_hidden(self):
        old = [dict(seq=1, busy_cycles=10), dict(seq=2, busy_cycles=20)]
        new = [dict(seq=1, busy_cycles=11), dict(seq=2, busy_cycles=19)]
        result = compare_commands(old, new)
        self.assertFalse(result['identical'])
        self.assertEqual(result['changed_commands'], 2)

    def test_command_schema_and_count_strict(self):
        old = [dict(seq=1, busy_cycles=10)]
        self.assertTrue(compare_commands(old, copy.deepcopy(old))['identical'])
        for new in ([], [dict(seq=1)]):
            with self.assertRaises(ValueError):
                compare_commands(old, new)

    def test_command_difference_report_is_bounded_not_count(self):
        old = [dict(seq=i, busy_cycles=10) for i in range(60)]
        new = [dict(seq=i, busy_cycles=11) for i in range(60)]
        result = compare_commands(old, new)
        self.assertEqual(result['changed_commands'], 60)
        self.assertEqual(len(result['first_differences']), 50)
        self.assertTrue(result['differences_truncated'])


if __name__ == '__main__':
    unittest.main()
