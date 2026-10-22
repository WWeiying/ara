"""New parameter binding only; frozen full-oracle tests remain applicable unchanged."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import qualify_pure_war_budget900_terminal as q


class SuccessorBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = q.life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.runner.PRE_SEAL)
        cls.old = q.life.read_bound(q.runner.OLD_PREPARED, q.runner.OLD_SEAL)
    def setUp(self):
        self.run = q.life.OUT / 'test900-never-launched'
        self.prepared = dict(self.old, output=str(self.run), command=q.runner.command(self.run), timeout_s=900,
            same_ELF=True, software_or_RTL_modified=False, old_VDB_reused=False,
            predecessor=str(q.runner.OLD_RUN), predecessor_prepared_seal=q.runner.OLD_SEAL,
            predecessor_status='TIMEOUT_NOT_QUALIFIED_NOT_ADMITTED')
    def binding(self):
        with patch.object(q.runner.original, 'validate'): q.binding(self.pre, self.prepared, self.run)
    def test_complete_binding(self): self.binding()
    def test_reject600(self):
        self.prepared['timeout_s'] = 600
        with self.assertRaises(ValueError): self.binding()
    def test_wrong_ELF(self):
        self.prepared['elf_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.binding()
    def test_wrong_scope(self):
        self.prepared = copy.deepcopy(self.prepared); self.prepared['targets'][0]['scope'] = 'wrong'
        with self.assertRaises(ValueError): self.binding()
    def test_old_VDB(self):
        self.prepared['old_VDB_reused'] = True
        with self.assertRaises(ValueError): self.binding()
    def test_wrong_run_binding(self):
        self.prepared['output'] = str(q.runner.OLD_RUN)
        with self.assertRaises(ValueError): self.binding()
    def test_unchanged_oracle_functions(self):
        self.assertEqual(q.frozen.RUN, q.runner.OLD_RUN)
        self.assertEqual(q.frozen.RUN_SEAL, q.runner.OLD_SEAL)
        self.assertEqual(q.runner.original.BUDGET, 600)
    def test_terminal_budget900_only(self):
        state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, case=q.p.NAME, timeout=False,
            coverage_admitted=False, admission_performed=False, terminal_oracle_verified=False, pid=1234)
        actual = dict(self.prepared, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
        started = dict(pid=1234, process_group=1234, budget_s=900, input_elf=str(q.runner.PRE / 'input.elf'),
            elf_sha256=q.runner.original.ELF_SEAL, image=str(q.life.IMAGE), image_sha256=q.runner.original.IMAGE_SEAL,
            command=self.prepared['command'], foreground_lifetime=True, coverage_admitted=False)
        q.terminal(state, actual, started, self.prepared)
        started['budget_s'] = 600
        with self.assertRaises(ValueError): q.terminal(state, actual, started, self.prepared)
    def test_timeout_not_qualifiable(self):
        with self.assertRaises(ValueError): q.terminal(dict(status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED'), {}, {}, self.prepared)
    def test_missing_terminal_not_collect(self):
        # Exercise the inherited mandatory terminal gate with isolated bindings, not the real run.
        from types import FunctionType
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            run = Path(tmp) / 'missing'; out = q.life.OUT / 'test900-no-artifacts'
            plan = dict(status=q.frozen.PLAN_STATUS, run=str(run), preflight_seal=q.runner.PRE_SEAL,
                        parent_prepared_seal='0' * 64, pins={})
            context = dict(q.frozen.collect.__globals__, RUN=run, runner=q.runner, RUN_SEAL='0' * 64)
            with patch.object(q.life, 'read_bound', return_value=plan), patch.object(q.life, 'check'), self.assertRaisesRegex(ValueError, 'no terminal status'):
                FunctionType(q.frozen.collect.__code__, context)(Path(tmp) / 'plan', '0' * 64, out)
            self.assertFalse(out.exists())


if __name__ == '__main__': unittest.main()
