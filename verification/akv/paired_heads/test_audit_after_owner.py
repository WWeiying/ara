#!/usr/bin/env python3
"""Audit is never invoked if the live-owner gate rejects completion."""
import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_after_owner as r


class AuditGateTest(unittest.TestCase):
    def test_gate_rejection_preserves_nonexecution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root/'original'
            run.mkdir()
            args = argparse.Namespace(run=run, control=root/'control', output=root/'audit',
                                      owner_pid=123, wait_timeout=10)
            with patch.object(r, 'wait_owner', side_effect=ValueError('Not terminal PASS')), \
                    patch.object(r, 'audit') as audit:
                with self.assertRaises(ValueError):
                    r.run(args)
                audit.assert_not_called()
                self.assertFalse(args.output.exists())
                self.assertEqual(r.s.read_json(args.control/'status.json')['state'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
