import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

COVERAGE = Path(__file__).resolve().parents[1] / 'coverage'
sys.path.insert(0, str(COVERAGE))
import extend_vcs_dve_batch as extension


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.elf = Path(self.temp.name) / 'test.elf'
        self.elf.write_bytes(b'unique input')
        self.catalog = SimpleNamespace(tests={
            'rvv:new': SimpleNamespace(kind='rvv', binary=self.elf)})
        self.old = {'cases': []}

    def test_new_input(self):
        self.assertEqual(len(extension.select_tests(self.catalog, self.old, ['rvv:new'])), 1)

    def test_duplicate_name(self):
        with self.assertRaises(ValueError):
            extension.select_tests(self.catalog, self.old, ['rvv:new', 'rvv:new'])

    def test_duplicate_binary(self):
        self.old['cases'] = [{'test': 'rvv:old', 'elf_sha256': extension.batch.sha256(self.elf)}]
        with self.assertRaises(ValueError):
            extension.select_tests(self.catalog, self.old, ['rvv:new'])

    def test_missing_binary(self):
        self.elf.unlink()
        with self.assertRaises(ValueError):
            extension.select_tests(self.catalog, self.old, ['rvv:new'])

    def test_empty(self):
        with self.assertRaises(ValueError):
            extension.select_tests(self.catalog, self.old, [])


if __name__ == '__main__':
    unittest.main()
