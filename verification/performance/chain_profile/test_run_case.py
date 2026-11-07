import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('chain_run_case', Path(__file__).with_name('run_case.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class TestExecutionGates(unittest.TestCase):
    def test_json_encoder_does_not_receive_print_options(self):
        tree = ast.parse(Path(runner.__file__).read_text())
        for call in ast.walk(tree):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'dumps':
                self.assertNotIn('flush', [item.arg for item in call.keywords])

    def fixture(self, root):
        elf = root / 'test.elf'
        elf.write_bytes(b'\x7fELFtest')
        runner.save(root / 'source-pins.json', {str(elf): runner.digest(elf)})
        record = dict(state='BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=runner.digest(elf),
                      source_pins_sha256=runner.digest(root / 'source-pins.json'), artifacts={})
        runner.save(root / 'build.json', record)
        return record, elf

    def test_software_accepts_only_sealed_elf(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            record, elf = self.fixture(root)
            accepted, pins = runner.checked_software(root)
            self.assertEqual(accepted, record)
            self.assertIn(str(elf), pins)
            elf.write_bytes(b'\x7fELFdrift')
            with self.assertRaises(ValueError):
                runner.checked_software(root)

    def test_rejects_failed_build_and_inventory_drift(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            record, _ = self.fixture(root)
            record['state'] = 'FAIL'
            runner.save(root / 'build.json', record)
            with self.assertRaises(ValueError):
                runner.checked_software(root)
            record['state'] = 'BUILT_NOT_EXECUTED'
            runner.save(root / 'build.json', record)
            runner.save(root / 'source-pins.json', {})
            with self.assertRaises(ValueError):
                runner.checked_software(root)

    def test_eoc_does_not_hide_error(self):
        runner.successful_log('Core Test *** SUCCESS ***')
        for text in ('no completion', 'Core Test *** SUCCESS ***\nError: wrong',
                     'Core Test *** SUCCESS ***\nFAILED', 'Fatal: exit'):
            with self.assertRaises(ValueError):
                runner.successful_log(text)


if __name__ == '__main__':
    unittest.main()
