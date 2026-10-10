"""Only mocked lifecycle; same frozen input and separate900 budget binding."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import run_pure_war_budget900_successor as r


class SuccessorTests(unittest.TestCase):
    def test_frozen_original_budget_untouched(self):
        self.assertEqual(r.original.BUDGET, 600); self.assertEqual(r.BUDGET, 900)
        self.assertIs(r.run.__code__, r.original.run.__code__)
        self.assertEqual(r.run.__globals__['BUDGET'], 900)
    def test_command_same_input_not_old_VDB(self):
        out = r.life.OUT / 'test-never-launched'
        cmd = r.command(out)
        self.assertIn('+PRELOAD=' + str(r.PRE / 'input.elf'), cmd); self.assertIn('+NO_FSDB', cmd)
        self.assertEqual(cmd[cmd.index('-cm_dir') + 1], str(out / 'code.vdb'))
        self.assertNotIn(str(r.OLD_RUN / 'code.vdb'), cmd)
    def test_predecessor_seal_inputs(self):
        old = r.life.read_bound(r.OLD_PREPARED, r.OLD_SEAL)
        self.assertEqual(old['elf_sha256'], r.original.ELF_SEAL)
        self.assertEqual(old['preflight_seal'], r.PRE_SEAL)
    def test_same_preflight_contract(self):
        pre = r.life.read_bound(r.PRE / 'preflight-manifest.json', r.PRE_SEAL)
        self.assertEqual(pre['reference_counts']['matched_instructions'], 241635)
        self.assertEqual(pre['checks'], 1765)
    def test_existing_rejected(self):
        with self.assertRaises(ValueError): r.prepare(r.OLD_RUN)
    def run_fake(self, timeout=False, code=0):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'; proc = Mock(pid=12345678, returncode=code)
            proc.wait.return_value = code; proc.poll.return_value = code
            manifest = dict(timeout_s=900, command=r.command(out), output=str(out), pins={})
            if timeout:
                proc.wait.side_effect = [subprocess.TimeoutExpired(manifest['command'], 900), -9]
                proc.poll.return_value = None; proc.returncode = -9
            with patch.object(r.life, 'OUT', Path(tmp)), patch.object(r.original.subprocess, 'Popen', return_value=proc) as popen, patch.object(r.original.os, 'killpg') as kill:
                if timeout:
                    with self.assertRaises(subprocess.TimeoutExpired): r.run(out, manifest)
                    kill.assert_called_once_with(proc.pid, r.original.signal.SIGKILL)
                elif code:
                    with self.assertRaises(ValueError): r.run(out, manifest)
                else: r.run(out, manifest)
                self.assertEqual(popen.call_count, 1)
            status = json.loads((out / 'simulation-status.json').read_bytes())
            start = json.loads((out / 'started.json').read_bytes()); self.assertEqual(start['budget_s'], 900)
            self.assertFalse(status['coverage_admitted']); self.assertFalse(status['terminal_oracle_verified'])
            self.assertEqual(proc.wait.call_args_list[0].kwargs['timeout'], 900)
            return status
    def test_foreground900(self): self.assertEqual(self.run_fake()['returncode'], 0)
    def test_timeout900_cleanup(self): self.assertTrue(self.run_fake(timeout=True)['process_group_cleanup'])
    def test_nonzero_preserved(self): self.assertEqual(self.run_fake(code=7)['returncode'], 7)
    def test600_rejected_no_launch(self):
        out = r.life.OUT / 'test-never-launched'
        with patch.object(r.original.subprocess, 'Popen') as popen, self.assertRaises(ValueError):
            r.run(out, dict(timeout_s=600, command=r.command(out), output=str(out), pins={}))
        popen.assert_not_called()


if __name__ == '__main__': unittest.main()
