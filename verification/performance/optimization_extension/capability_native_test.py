"""Verify test selection does not request or fabricate backend/AXI activity."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('capability_native', Path(__file__).with_name('capability_native_run.py'))
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)


class NativeSelection(unittest.TestCase):
    def test_exact_class_selection(self):
        argv = n.command(dict(simv='image'), Path('firmware.elf'), Path('run'), 1)
        self.assertEqual([s for s in argv if s.startswith('+UVM_TESTNAME=')],
                         ['+UVM_TESTNAME=ara_cvxif_smoke_test'])
        self.assertIn('+PRELOAD=firmware.elf', argv)
        self.assertEqual(argv[0], 'image')
        self.assertFalse(any('override' in s.lower() or 'severity' in s.lower() for s in argv))

    def test_existing_real_env_both_images(self):
        c = n.base()
        for directory in (c.OLD, c.NEW):
            self.assertTrue(n.checked_class(c, directory)['real_soc_binding'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
