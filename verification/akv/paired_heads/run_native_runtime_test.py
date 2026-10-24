"""Synthetic fail-closed tests; never launch a simulator."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run_native_runtime as r


class WorkerTests(unittest.TestCase):
    def test_terminal_prerequisite_required(self):
        for state in ('RUNNING','FAIL','TIMEOUT','PREFLIGHT_PASS_NOT_RUN'):
            with self.subTest(state=state),tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/'status.json').write_text(json.dumps(dict(state=state,child_pid=None)))
                (root/'result.json').write_text(json.dumps(dict(state=state)))
                with self.assertRaisesRegex(ValueError,'terminal PASS'):
                    r.checked_prerequisite(root,{})

    def test_pins_failure_never_dispatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'build').mkdir()
            (root/'previous').mkdir()
            a = argparse.Namespace(build=root/'build',prerequisite=root/'previous',output=root/'run',
                                   timeout=10800,build_preflight_only=False)
            with patch.object(r,'checked_build',side_effect=ValueError('source drift')), \
                 patch.object(r.context.Execution,'execute') as execute:
                with self.assertRaisesRegex(ValueError,'source drift'):
                    r.run(a)
                execute.assert_not_called()
            status = json.loads((root/'run/status.json').read_text())
            self.assertEqual(status['state'],'FAIL')
            self.assertIsNone(status['child_pid'])


if __name__ == '__main__':
    unittest.main()
