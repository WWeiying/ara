import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('gates', Path(__file__).parents[1] /
                                              'ethernet/check_rebuild_reports.py')
gates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gates)


def timing(hold='-0.100', clock='clk', setup='0.100'):
    labels = ['WNS(ns)', 'TNS(ns)', 'TNS Failing Endpoints', 'TNS Total Endpoints',
              'WHS(ns)', 'THS(ns)', 'THS Failing Endpoints', 'THS Total Endpoints',
              'WPWS(ns)', 'TPWS(ns)', 'TPWS Failing Endpoints', 'TPWS Total Endpoints']
    values = [setup, '0.000', '0', '100', hold, '-0.100', '1', '100', '0.200', '0.000', '0', '100']
    header = '  '.join(labels)
    def table(names, row):
        return ('  '.join(n.ljust(30) for n in names) + '\n' +
                '  '.join('-'*30 for n in names) + '\n' +
                '  '.join(v.ljust(30) for v in row) + '\n\n')
    return (header + '\n' + '-'*50 + '\n' + ' '.join(values) + '\n' +
            '| Intra Clock Table\n' + table(['Clock', *labels], [clock, *values]) +
            '| Inter Clock Table\n' + table(['From Clock', 'To Clock', *labels[:8]],
                ['clk', 'other', '0.100', '0.000', '0', '10', '0.050', '0.000', '0', '10']))


CDC = '''ID Severity Count Description
CDC-1 Critical 1 unknown
Source Clock: a
Destination Clock: b
CDC Type: User Ignored
1 CDC-1 Critical unknown 0 False Path a/reg/C b/reg/D
'''


class ReportTests(unittest.TestCase):
    def test_known_synthesis_deferral(self):
        self.assertTrue(gates.synthesis(timing(), timing())['setup_passed'])

    def test_setup_failure(self):
        with self.assertRaises(ValueError):
            gates.synthesis(timing(setup='-0.001'), timing())

    def test_worse_hold(self):
        with self.assertRaises(ValueError):
            gates.synthesis(timing(hold='-0.101'), timing())

    def test_new_clock(self):
        with self.assertRaises(ValueError):
            gates.synthesis(timing(clock='new_clock'), timing())

    def test_missing_table(self):
        with self.assertRaises(ValueError):
            gates.synthesis(timing().replace('Inter Clock Table', 'missing'), timing())

    def test_missing_inventory(self):
        with self.assertRaises(ValueError):
            gates.synthesis(timing().replace('-0.100 1 100', '-0.100 2 100'), timing())

    def test_nan(self):
        with self.assertRaises(ValueError):
            gates.summary(timing(setup='NaN'))

    def test_cdc_counts_not_enough(self):
        old = gates.cdc_rows(CDC)
        new = gates.cdc_rows(CDC.replace('b/reg/D', 'b/new/D'))
        self.assertEqual(sum(old.values()), sum(new.values()))
        self.assertTrue(new - old)

    def test_cdc_missing_details(self):
        with self.assertRaises(ValueError):
            gates.cdc_rows(CDC.replace('Critical 1 unknown', 'Critical 2 unknown'))

    def test_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'timing_summary.rpt').write_text(timing(hold='0.100').replace('-0.100 1 100', '0.000 0 100'))
            (root/'check_timing.rpt').write_text('\n'.join('checking ' + c + ' (0)' for c in
                ('no_clock', 'unconstrained_internal_endpoints', 'multiple_clock',
                 'generated_clocks', 'loops', 'latch_loops')))
            for name in ('drc', 'methodology'):
                (root/(name+'.rpt')).write_text('Violations found: 1\n| ABC | Warning | detail |')
            (root/'cdc.rpt').write_text(CDC)
            self.assertFalse(gates.release(root, CDC)['cdc_signoff'])
            (root/'drc.rpt').write_text('Violations found: 1\n| ABC | Critical Warning | detail |')
            with self.assertRaises(ValueError):
                gates.release(root, CDC)


if __name__ == '__main__':
    unittest.main()
