import copy
import unittest
import audit_raw741_export as t


class IdentityContract(unittest.TestCase):
    def setUp(self):
        inputs = ['design'] + ['vdb%d' % i for i in range(741)]
        selected = ['test%d' % i for i in range(741)]
        hierarchy = [('row%d' % i, '1') for i in range(2989)]
        self.args = [inputs, selected, list(inputs), list(selected),
                     'DVE_SELECTED_TESTS: ' + ' '.join(selected) + '\nDVE_COVERAGE_EXPORT_DONE\n',
                     dict(mode='off', status='DISABLED', waived_report=None, raw_report='summary.csv'),
                     hierarchy, list(hierarchy), []]

    def test_exact_contract(self):
        t.identity_contract(*self.args)

    def test_inputs_and_selected_reorder_missing_duplicate(self):
        for index in (2, 3):
            for mutation in ('reorder', 'missing', 'duplicate'):
                args = copy.deepcopy(self.args)
                values = args[index]
                if mutation == 'reorder':
                    values[0], values[1] = values[1], values[0]
                elif mutation == 'missing':
                    values.pop()
                else:
                    values[-1] = values[0]
                with self.assertRaises(ValueError):
                    t.identity_contract(*args)

    def test_gui_mismatch_duplicate_marker_and_failure(self):
        for gui in ('DVE_COVERAGE_EXPORT_DONE\n', self.args[4] * 2,
                    self.args[4] + 'DVE_COVERAGE_EXPORT_FAILED: error\n'):
            args = copy.deepcopy(self.args)
            args[4] = gui
            with self.assertRaises(ValueError):
                t.identity_contract(*args)

    def test_same_count_wrong_full_hierarchy(self):
        for changed in ([('foreign', '1')] + self.args[7][1:], self.args[7][::-1],
                        [(self.args[7][0][0], '2')] + self.args[7][1:]):
            args = copy.deepcopy(self.args)
            args[7] = changed
            with self.assertRaises(ValueError):
                t.identity_contract(*args)

    def test_waiver_and_exclusion_rejected(self):
        for field, value in (('mode', 'auto'), ('status', 'PREPARED'),
                             ('waived_report', 'summary_waived.csv')):
            args = copy.deepcopy(self.args)
            args[5][field] = value
            with self.assertRaises(ValueError):
                t.identity_contract(*args)
        args = copy.deepcopy(self.args)
        args[8] = ['exclusions.el']
        with self.assertRaises(ValueError):
            t.identity_contract(*args)

    def test_actual_raw740_hierarchy(self):
        rows = t.hierarchy(t.report.PRIOR)
        self.assertEqual(len(rows), 2989)
        self.assertIn(('uvm_custom_install_verdi_recording', '0'), rows)


if __name__ == '__main__':
    unittest.main()
