import unittest

import run


class CasesTest(unittest.TestCase):
    def test_focused_originals_and_controls(self):
        suite = run.cases(False)
        self.assertEqual(len(suite), 8)
        for case in suite:
            self.assertEqual(case['flags'], 0 if 'all_off' in case['name'] else 16)
            expected = {16: (0x7c00, 0x7e00), 32: (0x7f800000, 0x7fc00000)}
            self.assertEqual(case['bits'], expected[case['width']][bool(case['flags'])])

    def test_extended_shape_and_sticky_coverage(self):
        suite = run.cases(True)
        self.assertEqual(len(suite), 166)
        self.assertEqual(len({case['name'] for case in suite}), len(suite))
        original = [case for case in suite if case['name'].startswith('rvv_small_')]
        self.assertEqual(len(original), 110)
        self.assertEqual({case['rm'] for case in original}, set(range(5)))
        self.assertEqual({case['prior'] for case in original}, {0, 1})
        for case in original:
            self.assertEqual(case['flags'], 16 | case['prior'])
        for case in suite:
            if case['name'].startswith('inactive_snan'):
                self.assertEqual(case['flags'], 1)
            if case['name'].startswith('positive_only'):
                self.assertEqual(case['flags'], 0)


if __name__ == '__main__':
    unittest.main()
