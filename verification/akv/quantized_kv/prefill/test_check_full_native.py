import unittest

from check_full_native import SCOPE, check_full_log
from test_check_native import fixture


class FullCheckerTest(unittest.TestCase):
    def test_complete(self):
        text, golden = fixture()
        result = check_full_log(SCOPE + '\n' + text, golden, 1)
        self.assertTrue(result['whole_call'])
        self.assertTrue(result['admission_included'])
        self.assertTrue(result['scatter_included'])
        self.assertEqual(result['baseline_cycles'], 100)

    def test_reject_scheduler_or_scope_drift(self):
        text, golden = fixture()
        for candidate in (text, SCOPE + '\n' + SCOPE + '\n' + text,
                          text + '\n' + SCOPE,
                          SCOPE.replace('scatter=1', 'scatter=0') + '\n' + text,
                          SCOPE + '\nPREFILL_SCOPE other\n' + text):
            with self.subTest(candidate=candidate[:100]), self.assertRaises(ValueError):
                check_full_log(candidate, golden, 1)

    def test_numeric_and_activity_gates_preserved(self):
        text, golden = fixture()
        for old, new in [('commands=4', 'commands=0'), ('errors=0', 'errors=1'),
                         ('3f800000', '7fc00000'), ('PREFILL_SUITE_PASS', '')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_full_log(SCOPE + '\n' + text.replace(old, new, 1), golden, 1)


if __name__ == '__main__':
    unittest.main()
