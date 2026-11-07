import ast
import importlib.util
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location('akv_pair_eval_owner', Path(__file__).with_name('run.py'))
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class TestOwner(unittest.TestCase):
    def test_runtime_root_is_actual_repository(self):
        self.assertEqual(owner.ROOT, Path(__file__).resolve().parents[3])

    def test_conflicting_hardware_and_software_identities_rejected(self):
        self.assertEqual(owner.combine({'x': 'a'}, {'x': 'a', 'y': 'b'}), {'x': 'a', 'y': 'b'})
        with self.assertRaises(ValueError): owner.combine({'x': 'a'}, {'x': 'changed'})

    def test_zero_exit_or_completion_marker_is_not_enough(self):
        for text in ('no completion', 'Core Test *** SUCCESS ***\nError: bad',
                     'Core Test *** SUCCESS ***\nFAILED'):
            with self.assertRaises(ValueError): owner.successful_log(text)

    def test_print_options_are_not_passed_to_json_encoder(self):
        tree = ast.parse(Path(owner.__file__).read_text())
        for call in ast.walk(tree):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'dumps':
                self.assertNotIn('flush', [keyword.arg for keyword in call.keywords])

    def test_unknown_checker_rejected(self):
        with self.assertRaises(ValueError): owner.load_checker('../unexpected')


if __name__ == '__main__':
    unittest.main()
