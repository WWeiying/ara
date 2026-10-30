"""Fail-closed worker checks with mocked preparation, not simulator execution."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run_prefill_slice as r


class WorkerTests(unittest.TestCase):
    def test_checker_is_exact_f32_module_not_parent_namesake(self):
        self.assertEqual(Path(r.leaf_check.__file__).resolve(),r.HERE/'rtl_check.py')
        self.assertEqual(r.leaf_check.EXPECTED['commands'],396)

    def test_preflight_failure_never_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'build').mkdir()
            (root/'prior').mkdir()
            args = argparse.Namespace(build=root/'build',prerequisite=root/'prior',output=root/'run',
                                      timeout=10800,preflight_only=False)
            with patch.object(r,'inputs',side_effect=ValueError('drift')), \
                 patch.object(r.Execution,'execute') as execute:
                with self.assertRaisesRegex(ValueError,'drift'):
                    r.run(args)
                execute.assert_not_called()
            status = json.loads((root/'run/status.json').read_text())
            self.assertEqual(status['state'],'FAIL')
            self.assertIsNone(status['child_pid'])


if __name__ == '__main__':
    unittest.main()
