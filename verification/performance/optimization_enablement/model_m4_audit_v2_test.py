"""Framing regression: preserve the original checker's strict comparisons."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load('model_m4_audit', HERE / 'model_m4_audit_v2.py')
old = load('model_m4_original_tests', HERE / 'model_m4_test.py')


class Framing(unittest.TestCase):
    def check(self, rows):
        repairs = []
        value = old.m.check(audit.records(rows, {'qbs': 0x1000, 'producer': 0x2000}, repairs),
                            {'qbs': 0x1000, 'producer': 0x2000}, vocab=2)
        return value, repairs

    def collision(self):
        return [audit.PREFIX + row if row.startswith('Trace 0: 0xaa') else row for row in old.fixture()]

    def test_unmodified_complete(self):
        self.assertEqual(self.check(old.fixture())[1], [])

    def test_two_missing_records_recovered(self):
        value, repairs = self.check(self.collision())
        self.assertEqual(len(repairs), 2)
        self.assertEqual(value['native_entries'], [{'qbs': 2}, {'qbs': 2, 'producer': 1}])

    def test_original_checker_still_fails_collision(self):
        with self.assertRaisesRegex(ValueError, 'Native QBS entries'):
            old.m.check(self.collision(), {'qbs': 0x1000, 'producer': 0x2000}, vocab=2)

    def test_wrong_prefix_rejected(self):
        rows = self.collision()
        rows[1] = rows[1].replace(audit.PREFIX, 'unexpected text')
        with self.assertRaisesRegex(ValueError, 'framing'):
            self.check(rows)

    def test_non_native_pc_collision_rejected(self):
        rows = self.collision()
        rows[1] = rows[1].replace('/1000/', '/2000/')
        with self.assertRaisesRegex(ValueError, 'framing'):
            self.check(rows)

    def test_numerical_difference_not_hidden(self):
        rows = self.collision()
        rows[rows.index('M4_BITS index=0 00000000 3f800000')] = 'M4_BITS index=0 00000000 40000000'
        with self.assertRaisesRegex(ValueError, 'Logits'):
            self.check(rows)

    def test_extra_command_not_tolerated(self):
        rows = self.collision()
        rows.insert(2, 'Trace 0: 0xaa [0/1000/0/0] qbs')
        with self.assertRaisesRegex(ValueError, 'Native QBS entries'):
            self.check(rows)

    def test_truncation_not_tolerated(self):
        with self.assertRaises(ValueError):
            self.check(self.collision()[:-1])


if __name__ == '__main__':
    suite = unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromTestCase(old.Checker),
                                unittest.defaultTestLoader.loadTestsFromTestCase(Framing)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
