"""Worker phase/error tests with synthetic children; never execute a simulator."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_context as worker


class ExecutionTests(unittest.TestCase):
    def test_success_tracks_real_child_and_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            owner = worker.Execution(out)
            def child(argv, log, timeout, env, started):
                started(12345)
                state = json.loads((out/'status.json').read_text())
                self.assertEqual(state['state'], 'RUNNING')
                self.assertEqual(state['child_pid'], 12345)
                self.assertEqual(state['simulator_pid'], 12345)
                self.assertEqual(timeout, 17)
                self.assertNotIn('LD_PRELOAD', env)
                return 0
            with patch.object(worker.s, 'run_command', side_effect=child):
                owner.execute(['synthetic'], out/'console.log', 17, 'RUNNING')
            self.assertIsNone(owner.state['child_pid'])
            self.assertEqual(owner.state['running_exit_code'], 0)

    def test_failure_and_timeout_clear_child(self):
        for fail in ('exit', 'timeout'):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as tmp:
                owner = worker.Execution(Path(tmp))
                def child(argv, log, timeout, env, started):
                    started(12345)
                    if fail == 'timeout':
                        raise subprocess.TimeoutExpired(argv, timeout)
                    return 7
                with patch.object(worker.s, 'run_command', side_effect=child):
                    with self.assertRaises((ValueError, subprocess.TimeoutExpired)):
                        owner.execute(['synthetic'], Path(tmp)/'console.log', 17, 'RUNNING')
                self.assertIsNone(owner.state['child_pid'])

    def test_preflight_failure_is_terminal_and_never_executes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('build', 'prerequisite', 'prerequisite_build', 'gate'):
                (root/name).mkdir()
            args = argparse.Namespace(timeout=10800, output=root/'out', preflight_only=False,
                **{name:root/name for name in ('build','prerequisite','prerequisite_build','gate')})
            with patch.object(worker, 'prepare_inputs', side_effect=ValueError('drift')), \
                 patch.object(worker.s, 'run_command') as run:
                with self.assertRaisesRegex(ValueError, 'drift'):
                    worker.run(args)
                run.assert_not_called()
            status = json.loads((root/'out/status.json').read_text())
            result = json.loads((root/'out/result.json').read_text())
            self.assertEqual(status['state'], 'FAIL')
            self.assertEqual(result['state'], 'FAIL')
            self.assertIsNone(status['child_pid'])


if __name__ == '__main__':
    unittest.main()
