from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_failed_repair_20261008_v2 as runner


class LaunchContracts(unittest.TestCase):
    def test_all_original_elf_launch_contracts(self):
        image = Path('/tmp/current-image/simv')
        for name in runner.FOCUSED + runner.NEIGHBOURS:
            with self.subTest(name=name):
                command = runner.simulation_command(image, runner.source(name), name)
                self.assertEqual(command[0], str(image))
                self.assertIn('+PRELOAD=' + str(runner.source(name) / 'input.elf'), command)
                if name in runner.custom.NAMES or name in runner.COUNTS or name in ('axpy', 'qbs_canonical'):
                    self.assertFalse(any(a.startswith('+COMMIT_TOHOST=') for a in command))
                else:
                    self.assertIn('+COMMIT_TOHOST=80001000', command)

    def test_fault_layout_probe_enabled(self):
        command = runner.simulation_command(Path('/tmp/simv'), runner.source('gap71_qbs_fault'), 'gap71_qbs_fault')
        self.assertIn('+ARA_DEBUG_EEW', command)

    def test_failed_original_not_automatically_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / 'results/example'
            old.mkdir(parents=True)
            runner.base.save(old / 'audit.json', {'status': 'FAIL'})
            with self.assertRaisesRegex(RuntimeError, 'previous case did not pass'):
                runner.reuse_pass(root, 'example', root, root / 'simv', root)

    def test_started_without_receipt_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / 'results/example'
            old.mkdir(parents=True)
            runner.base.save(old / 'started.json', {'pid': 1})
            with self.assertRaisesRegex(RuntimeError, 'incomplete evidence'):
                runner.reuse_pass(root, 'example', root, root / 'simv', root)

    def test_reuse_rejects_other_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / 'results/example'
            old.mkdir(parents=True)
            runner.base.save(old / 'audit.json', {'status': 'PASS'})
            runner.base.save(root / 'source-pins.json', {'image': 'old'})
            runner.base.save(root / 'build-image.json', {'image': 'new'})
            runner.base.save(root / 'build-source-pins.json', {})
            with patch.object(runner.base, 'check'), self.assertRaisesRegex(RuntimeError, 'same build/source'):
                runner.reuse_pass(root, 'example', root, root / 'simv', root)


if __name__ == '__main__':
    unittest.main()
