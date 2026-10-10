"""Runner refusals and mocked foreground lifecycle only; never starts VCS."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import run_pure_war_simulation as r


class RunnerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.pre = r.life.read_bound(r.PRE / 'preflight-manifest.json', r.PRE_SEAL)
    def validate(self, pre):
        with patch.object(r.preflight, 'target_binding', return_value=(self.pre['targets'], {})):
            r.validate(pre)
    def test_actual_contract(self): self.validate(self.pre)
    def test_budget(self):
        p = copy.deepcopy(self.pre); p['backend_budget_seconds'] = 601
        with self.assertRaises(ValueError): self.validate(p)
    def test_false_spike_oracle(self):
        p = copy.deepcopy(self.pre); p['validation']['skipped_unknown_bytes'] = 1
        with self.assertRaises(ValueError): self.validate(p)
    def test_elf_drift(self):
        p = copy.deepcopy(self.pre); p['pins'][str(r.PRE / 'input.elf')] = '0' * 64
        with self.assertRaises(ValueError): self.validate(p)
    def test_nonadjacent(self):
        p = copy.deepcopy(self.pre); p['symbols']['gpw_load'] += 4
        with self.assertRaises(ValueError): self.validate(p)
    def test_wrong_owner(self):
        p = copy.deepcopy(self.pre); p['targets'][0]['scope'] = 'wrong.port'
        with self.assertRaises(ValueError): self.validate(p)
    def test_missing_trace_pin(self):
        p = copy.deepcopy(self.pre); del p['pins'][str(r.PRE / 'spike.trace')]
        with self.assertRaises(ValueError): self.validate(p)
    def test_false_admission(self):
        p = copy.deepcopy(self.pre); p['coverage_admitted'] = True
        with self.assertRaises(ValueError): self.validate(p)
    def test_command_full_traces_no_fsdb(self):
        out = r.life.OUT / 'test-never-launched'
        cmd = r.command(out)
        self.assertIn('+NO_FSDB', cmd)
        self.assertIn('+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), cmd)
        self.assertIn('+VECTOR_TRACE=' + str(out / 'vector_trace.csv'), cmd)
        self.assertEqual(cmd[cmd.index('-cm') + 1], 'line+cond+fsm+tgl+branch')
        self.assertEqual(cmd[cmd.index('-cm_dir') + 1], str(out / 'code.vdb'))
        self.assertEqual(cmd.count('+PRELOAD=' + str(r.PRE / 'input.elf')), 1)
    def test_existing_directory_rejected(self):
        with self.assertRaises(ValueError): r.prepare(r.PRE)
    def test_bad_output_rejected(self):
        with self.assertRaises(ValueError): r.prepare(Path('/tmp/not-direct-run'))
    def test_supplement_pins(self):
        record = r.life.read_bound(r.SUPPLEMENT, r.SUPPLEMENT_SEAL)
        r.life.check(record['pins'])
        self.assertEqual(record['successor_result']['skipped'], 0)


class ForegroundLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.out = self.root / 'run'
        self.manifest = dict(timeout_s=600, command=r.command(self.out), output=str(self.out), pins={})
        self.process = Mock(pid=123456789, returncode=0)
        self.process.wait.return_value = 0
        self.process.poll.return_value = 0
    def execute(self):
        with patch.object(r.life, 'OUT', self.root), patch.object(r.subprocess, 'Popen', return_value=self.process) as popen:
            r.run(self.out, self.manifest)
        self.assertEqual(popen.call_count, 1)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
    def status(self): return json.loads((self.out / 'simulation-status.json').read_bytes())
    def test_success_not_pass_or_admit(self):
        self.execute(); status = self.status()
        self.assertEqual(status['returncode'], 0)
        self.assertEqual(status['status'], 'SIMULATION_EXITED_NOT_ADMITTED')
        self.assertFalse(status['terminal_oracle_verified']); self.assertFalse(status['coverage_admitted'])
        self.process.wait.assert_called_once_with(timeout=600)
        started = json.loads((self.out / 'started.json').read_bytes())
        self.assertEqual(started['pid'], started['process_group'])
        self.assertFalse(started['live_identity_verified'])
    def test_nonzero_preserved(self):
        self.process.wait.return_value = self.process.returncode = 7
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(self.status()['returncode'], 7)
        self.assertFalse(self.status()['coverage_admitted'])
    def test_timeout_kills_group_waits_records(self):
        self.process.poll.return_value = None; self.process.returncode = -9
        self.process.wait.side_effect = [subprocess.TimeoutExpired(self.manifest['command'], 600), -9]
        with patch.object(r.os, 'killpg') as kill, self.assertRaises(subprocess.TimeoutExpired): self.execute()
        kill.assert_called_once_with(self.process.pid, r.signal.SIGKILL)
        status = self.status(); self.assertTrue(status['timeout']); self.assertTrue(status['process_group_cleanup'])
        self.assertEqual(status['returncode'], -9)
        self.assertEqual(self.process.wait.call_count, 2)
    def test_command_drift_no_launch(self):
        self.manifest['command'] = self.manifest['command'] + ['+BAD_HINT']
        with patch.object(r.subprocess, 'Popen') as popen, self.assertRaises(ValueError): r.run(self.out, self.manifest)
        popen.assert_not_called()
    def test_timeout_drift_no_launch(self):
        self.manifest['timeout_s'] = 601
        with patch.object(r.subprocess, 'Popen') as popen, self.assertRaises(ValueError): r.run(self.out, self.manifest)
        popen.assert_not_called()


if __name__ == '__main__': unittest.main()
