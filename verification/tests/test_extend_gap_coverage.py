from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import extend_gap_coverage as gap


class GapSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.elf = Path(self.temp.name) / 'test.elf'
        self.elf.write_bytes(b'checked application')
        self.catalog = SimpleNamespace(tests={'app:new': SimpleNamespace(
            kind='app', binary=self.elf)})
        self.previous = {'cases': []}

    def test_application(self):
        self.assertEqual(len(gap.select_tests(self.catalog, self.previous, ['app:new'])), 1)

    def test_duplicate_elf(self):
        self.previous['cases'] = [{'test': 'rvv:old', 'elf_sha256': gap.batch.sha256(self.elf)}]
        with self.assertRaises(ValueError):
            gap.select_tests(self.catalog, self.previous, ['app:new'])

    def test_unsafe_name(self):
        with self.assertRaises(ValueError):
            gap.select_tests(self.catalog, self.previous, ['app:../old'])

    def test_duplicate_name(self):
        with self.assertRaises(ValueError):
            gap.select_tests(self.catalog, self.previous, ['app:new', 'app:new'])

    def test_missing_elf(self):
        self.elf.unlink()
        with self.assertRaises(ValueError):
            gap.select_tests(self.catalog, self.previous, ['app:new'])


if __name__ == '__main__':
    unittest.main()
