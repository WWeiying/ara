"""Normalize only trailing artifact newlines; also require identical AST."""
import ast
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
class TextContract(unittest.TestCase):
    def test_observer_only_relocated(self):
        prior=(HERE.parent/'full_e8_m8_block_prepare01/reference_successor01/reference_check.py').read_text()
        expected=prior.replace('HERE=Path(__file__).resolve().parent.parent',
                               'HERE=Path(__file__).resolve().parent')
        actual=(HERE/'reference_check.py').read_text()
        self.assertEqual(actual.rstrip('\n'),expected.rstrip('\n'))
        self.assertEqual(ast.dump(ast.parse(actual)),ast.dump(ast.parse(expected)))
