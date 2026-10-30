"""A failed owner or a drifting sealed queue must never dispatch an audit."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import queue_common_audit as q


class QueueAuditTest(unittest.TestCase):
    def check(self, effect=None):
        with tempfile.TemporaryDirectory(prefix='queue-common-audit-') as name:
            root = Path(name)
            run, build, prior, out, control = [root / leaf for leaf in ('run', 'build', 'prior', 'audit', 'control')]
            for directory in (run, build, prior): directory.mkdir()
            (run / 'status.json').write_text(json.dumps(dict(pid=123, state='RUNNING', build=str(build), prerequisite=str(prior))))
            (run / 'source-pins.json').write_text('{}')
            argv = ['queue', '--run', str(run), '--output', str(out), '--control', str(control), '--owner-pid', '123']
            with patch('sys.argv', argv), patch.object(q, 'checked_build', return_value=({}, {})), \
                    patch.object(q.s, 'hashes', return_value={}), patch.object(q.s, 'verify_pins'), \
                    patch.object(q, 'wait_owner', side_effect=effect) as wait, patch.object(q.os, 'execv') as execute:
                if effect:
                    with self.assertRaises(ValueError): q.main()
                else:
                    q.main()
                wait.assert_called_once_with(run.resolve(), 123, q.HERE / 'run_common_attention.py', 14400)
                if effect:
                    execute.assert_not_called()
                    self.assertEqual(json.loads((control / 'status.json').read_text())['state'], 'PREREQUISITE_NOT_ACCEPTED')
                else:
                    execute.assert_called_once()
                    self.assertEqual(json.loads((control / 'status.json').read_text())['state'], 'AUDIT_DISPATCHED')
                    self.assertIn(str(q.HERE / 'audit_common_attention.py'), execute.call_args.args[1])
            self.assertFalse(out.exists())

    def test_verified_owner_execs_auditor(self): self.check()
    def test_unaccepted_owner_does_not_dispatch(self): self.check(ValueError('owner failed'))


if __name__ == '__main__': unittest.main()
