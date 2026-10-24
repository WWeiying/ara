import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_after_verified_gate as worker


class GateWaitTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.gate = Path(tmp.name)
        self.owner = worker.ROOT / 'verification/akv/paired_heads/rtl_run.py'

    def status(self, state='RUNNING', child=123):
        (self.gate / 'status.json').write_text(json.dumps(
            dict(state=state, pid=42, child_pid=child)))
        (self.gate / 'result.json').write_text(json.dumps(dict(state=state)))

    def test_terminal_pass_never_opens_reused_pid(self):
        self.status('PASS', None)
        with patch.object(worker.os, 'pidfd_open', side_effect=AssertionError('must not open')):
            worker.wait_owner(self.gate, 42, self.owner, 1)

    def test_failed_or_unchecked_gate_does_not_launch(self):
        for state in ('FAIL', 'TIMEOUT', 'RUNNING', 'PREFLIGHT_PASS_NOT_RUN'):
            with self.subTest(state=state):
                self.status(state)
                with patch.object(worker.os, 'pidfd_open', side_effect=ProcessLookupError), \
                     self.assertRaises(ValueError):
                    worker.wait_owner(self.gate, 42, self.owner, 1)

    def test_mismatched_owner_is_rejected(self):
        self.status('PASS', None)
        with self.assertRaises(ValueError):
            worker.wait_owner(self.gate, 99, self.owner, 1)

    def test_live_owner_must_match_command_and_cwd(self):
        self.status()
        with patch.object(worker.os, 'pidfd_open', return_value=7), \
             patch.object(worker.os, 'close') as close, \
             patch.object(worker, 'owner_identity', return_value=([b'python3', b'wrong-script.py'], worker.ROOT)), \
             self.assertRaises(ValueError):
            worker.wait_owner(self.gate, 42, self.owner, 1)
        close.assert_called_once_with(7)

    def test_event_timeout_does_not_restart_owner(self):
        self.status()
        args = b'python3\0' + str(self.owner).encode() + b'\0'
        with patch.object(worker.os, 'pidfd_open', return_value=7), \
             patch.object(worker.os, 'close') as close, \
             patch.object(worker, 'owner_identity', return_value=(args.split(b'\0'), worker.ROOT)), \
             patch.object(worker.select, 'select', return_value=([], [], [])), \
             self.assertRaises(TimeoutError):
            worker.wait_owner(self.gate, 42, self.owner, 1)
        close.assert_called_once_with(7)

    def test_event_exit_rechecks_terminal_result(self):
        self.status()
        args = b'python3\0' + str(self.owner.relative_to(worker.ROOT)).encode() + b'\0'
        def ready(*_):
            self.status('PASS', None)
            return [7], [], []
        with patch.object(worker.os, 'pidfd_open', return_value=7), \
             patch.object(worker.os, 'close') as close, \
             patch.object(worker, 'owner_identity', return_value=(args.split(b'\0'), worker.ROOT)), \
             patch.object(worker.select, 'select', side_effect=ready):
            worker.wait_owner(self.gate, 42, self.owner, 1)
        close.assert_called_once_with(7)


if __name__ == '__main__':
    unittest.main()
