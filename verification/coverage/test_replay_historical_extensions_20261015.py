#!/usr/bin/env python3
"""Host-only replay safety tests. Never execute simv, Spike, or a compiler."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('extensions', Path(__file__).with_name('replay_historical_extensions_20261015.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cmd = ['oldsimv', '-l', 'run.vcs.log', '+PRELOAD=/old/input.elf',
                    '+TESTCASE=unit', '+NO_FSDB', '+ntb_random_seed=1',
                    '+COMMIT_TRACE=/old/commit_trace.csv', '+VECTOR_TRACE=/old/vector_trace.csv',
                    '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', '/old/code.vdb', '-cm_name', 'unit']

    def tearDown(self):
        self.tmp.cleanup()

    def test_redirect_all_outputs_preserve_stimulus(self):
        cmd = runner.rewrite(self.cmd, '/new/simv', self.root, self.root / 'input.elf')
        self.assertEqual(cmd[0], '/new/simv')
        self.assertFalse(any('/old/' in x for x in cmd))
        self.assertIn('+ntb_random_seed=1', cmd)
        self.assertIn('+TESTCASE=unit', cmd)
        self.assertEqual(runner.option(cmd, '-cm_dir'), str(self.root / 'code.vdb'))

    def test_unknown_argument_blocked(self):
        with self.assertRaisesRegex(ValueError, 'unreviewed'):
            runner.rewrite(self.cmd + ['+OTHER_OUTPUT=/old/file'], '/new/simv', self.root, self.root / 'input.elf')

    def test_duplicate_output_blocked(self):
        with self.assertRaises(ValueError):
            runner.rewrite(self.cmd + ['-cm_dir', '/elsewhere'], '/new/simv', self.root, self.root / 'input.elf')

    def test_ucli_frozen_dependencies_and_relative_output(self):
        nested = self.root / 'nested.tcl'
        nested.write_text('set f [open result.tsv w]\nrun\n')
        original = self.root / 'entry.tcl'
        original.write_text('source {' + str(nested) + '}\n')
        target = self.root / 'frozen'
        target.mkdir()
        pins = {}
        frozen = runner.freeze_tcl(original, target, pins)
        self.assertNotEqual(original, frozen)
        self.assertIn(str(target), frozen.read_text())
        self.assertNotIn(str(nested), frozen.read_text())
        runner.verify(pins)

    def test_ucli_external_write_blocked(self):
        source = self.root / 'unsafe.tcl'
        source.write_text('set f [open /tmp/old.tsv w]\n')
        with self.assertRaisesRegex(ValueError, 'absolute Tcl'):
            runner.freeze_tcl(source, self.root, {})

    def test_ucli_parent_escape_blocked(self):
        source = self.root / 'unsafe.tcl'
        source.write_text('set f [open ../old.tsv w]\n')
        with self.assertRaisesRegex(ValueError, 'unsafe Tcl'):
            runner.freeze_tcl(source, self.root, {})

    def test_pin_drift_rejected(self):
        source = self.root / 'input'
        source.write_text('original')
        pins = {str(source): runner.sha(source)}
        source.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'pin drift'):
            runner.verify(pins)

    def test_unknown_old_pass_not_acceptance(self):
        pins = {}
        recipe = runner.checker_recipe(797, Path('manifest.json'), self.cmd,
                                       {'vdb': '/old/code.vdb', 'status': 'PASS'}, pins)
        self.assertEqual(recipe['kind'], 'CHECKER_REQUIRED')

    def test_probe_requires_special_checker(self):
        recipe = runner.checker_recipe(600, Path('coverage.command.json'),
                                       self.cmd + ['-do', '/probe.tcl'], {}, {})
        self.assertEqual(recipe['kind'], 'CHECKER_REQUIRED')

    def test_red32_native_hold_not_pass(self):
        cmd = [s.replace('TESTCASE=unit', 'TESTCASE=vgap76_red32') for s in self.cmd]
        recipe = runner.checker_recipe(660, Path('rtl.command.json'), cmd, {'vdb': '/old/code.vdb'}, {})
        self.assertEqual(recipe['kind'], 'CHECKER_REQUIRED')

    def test_wrong_command_member_rejected(self):
        source = self.root / 'manifest.json'
        source.write_text(json.dumps({'command': self.cmd}))
        with self.assertRaisesRegex(ValueError, 'no original command'):
            runner.original_command(600, {'vdb': '/different/code.vdb', 'command_sources': [str(source)]})

    def test_exit17_not_overridden_by_checker(self):
        plan = dict(index=600, directory=str(self.root), work=str(self.root), status='PREPARED',
                    command=self.cmd, pins={}, timeout_s=10, executed=False, returncode=None)
        actual = dict(executed=True, returncode=17, elapsed_s=1, timed_out=False, cancelled=False)
        with patch.object(runner, 'child', return_value=actual) as run:
            result = runner.run_case(plan, lambda _: None)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['returncode'], 17)
        self.assertEqual(run.call_count, 1)

    def test_timeout_not_pass_even_rc0(self):
        plan = dict(index=600, directory=str(self.root), work=str(self.root), status='PREPARED',
                    command=self.cmd, pins={}, timeout_s=10, executed=False, returncode=None)
        actual = dict(executed=True, returncode=0, elapsed_s=1, timed_out=True, cancelled=False)
        with patch.object(runner, 'child', return_value=actual):
            self.assertEqual(runner.run_case(plan, lambda _: None)['status'], 'TIMEOUT')

    def test_contradictory_success_failure_rejected(self):
        (self.root / 'console.log').write_text('Core Test *** SUCCESS ***\nRVV_MASK_FAIL errors=1\n')
        (self.root / 'run.vcs.log').write_text('Core Test *** SUCCESS ***\n')
        plan = dict(pins={}, directory=str(self.root), work=str(self.root),
                    checker=dict(kind='CHECKER_REQUIRED', reason='unported'))
        with self.assertRaisesRegex(ValueError, 'raw failure veto'):
            runner.check_case(plan)

    def test_unknown_checker_clean_log_still_not_pass(self):
        for name in ('console.log', 'run.vcs.log'):
            (self.root / name).write_text('Core Test *** SUCCESS ***\n')
        plan = dict(pins={}, directory=str(self.root), work=str(self.root),
                    checker=dict(kind='CHECKER_REQUIRED', reason='unported'))
        self.assertEqual(runner.check_case(plan)['status'], 'CHECKER_REQUIRED')

    def test_checker_exception_preserves_simulator_numeric_exit(self):
        plan = dict(index=600, directory=str(self.root), work=str(self.root), status='PREPARED',
                    command=self.cmd, pins={}, timeout_s=10, executed=False, returncode=None)
        actual = dict(executed=True, returncode=0, elapsed_s=1, timed_out=False, cancelled=False)
        checker = dict(executed=True, returncode=17, elapsed_s=1, timed_out=False, cancelled=False)
        with patch.object(runner, 'child', side_effect=[actual, checker]):
            result = runner.run_case(plan, lambda _: None)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['checker_exit']['returncode'], 17)

    def test_real_ledger_198_static_prepare_no_process(self):
        self.assertEqual(runner.sha(runner.LEDGER), runner.LEDGER_SHA)
        members = runner.select_members(runner.read(runner.LEDGER))
        self.assertEqual([i for i, _ in members], list(range(600, 798)))
        with patch.object(runner.subprocess, 'Popen', side_effect=AssertionError('NO execution permitted')):
            rows = [runner.prepare_case(i, m, self.root, Path('/not-executed/simv')) for i, m in members]
        blocked = [(r['index'], r.get('reason')) for r in rows if r['status'] == 'BLOCKED']
        self.assertEqual(blocked, [])
        self.assertEqual(len(rows), 198)
        print('STATIC_198_PREPARE', json.dumps(dict(checkers=dict(runner.Counter(r['checker']['kind'] for r in rows)),
                                                  budgets=dict(runner.Counter(r['timeout_s'] for r in rows)),
                                                  executed=0)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
