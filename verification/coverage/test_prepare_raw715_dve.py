import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_raw715_dve as m


class Raw715Tests(unittest.TestCase):
    def test_actual715_members_and_all_metrics(self):
        inputs = (m.BASE / 'combined-inputs.txt').read_text().splitlines()
        selected, files = m.member_files(inputs)
        self.assertEqual(len(selected), 715)
        self.assertEqual(len(files), 6 + 715 * 5)

    def test_duplicate_or_wrong_population(self):
        inputs = (m.BASE / 'combined-inputs.txt').read_text().splitlines()
        for wrong in (inputs[:-1], inputs + [inputs[-1]], inputs[:-1] + [inputs[1]]):
            with self.assertRaises(ValueError):
                m.member_files(wrong)

    def test_missing_metric_fails_closed(self):
        with patch.object(Path, 'is_file', return_value=False):
            with self.assertRaisesRegex(ValueError, 'metric'):
                m.member_files((m.BASE / 'combined-inputs.txt').read_text().splitlines())

    def test_raw707_summary_actual_complete_depth_tree(self):
        rows = m.summary_rows(m.REFERENCE / 'summary.csv')
        self.assertGreater(len(rows), 2000)
        self.assertTrue(any('.' in r['Name'] for r in rows))

    def test_missing_metric_column_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'summary.csv'
            m.save(p, 'Name,Depth,Line\nara_tb,0,10.00%\n')
            with self.assertRaises(ValueError):
                m.summary_rows(p)

    def test_depth_jump_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'summary.csv'
            m.save(p, 'Name,Depth,Score,Line,Toggle,FSM,Condition,Branch\n'
                      'ara_tb,0,10%,10%,10%,NA,10%,10%\n'
                      'dut,2,10%,10%,10%,NA,10%,10%\n')
            with self.assertRaises(ValueError):
                m.summary_rows(p)

    def test_warning_and_waiver_guards_in_sealed_wrapper(self):
        text = m.WRAPPER.read_text()
        self.assertIn('diagnostics != 0', text)
        self.assertIn('unset DVE_REVIEWED_WAIVERS', text)
        self.assertIn('DVE_WAIVERS:-auto', text)
        self.assertNotIn('simulate', m.command(Path('/report'), Path('/inputs')))

    def test_controlled_environment_forces_off_and_unsets_DVE(self):
        identity = {'roles': {'launcher': '/vendor/bin/dve'}}
        with patch.object(m.tools, 'controlled_environment', return_value={'DVE': '/wrong', 'DVE_WAIVERS': 'auto'}):
            env = m.environment(identity, {})
        self.assertNotIn('DVE', env)
        self.assertEqual(env['DVE_WAIVERS'], 'off')
        self.assertEqual(env['PATH'], '/vendor/bin:/usr/bin:/bin')

    def test_command_is_only_existing_DVE_export(self):
        self.assertEqual(m.command(Path('/report'), Path('/inputs')),
                         ['/bin/bash', str(m.WRAPPER), '/report', '--inputs-file', '/inputs'])

    def test_fresh_output_required_before_tool_or_process(self):
        with patch.object(m.tools, 'prepare') as identity, patch.object(m.subprocess, 'Popen') as process:
            with self.assertRaises(ValueError):
                m.prepare(m.BASE, m.BASE)
            identity.assert_not_called()
            process.assert_not_called()

    def test_expected_seal_cannot_be_resampled(self):
        with self.assertRaises(ValueError):
            m.life.read_bound(m.BASE / 'seals.json', '0' * 64)


if __name__ == '__main__':
    unittest.main()
