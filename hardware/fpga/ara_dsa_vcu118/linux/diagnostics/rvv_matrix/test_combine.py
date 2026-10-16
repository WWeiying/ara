import unittest
from combine import numerical_pass


class NumericalPassTests(unittest.TestCase):
    def test_unique_positive_numerical_result(self):
        case = dict(pass_marker='RVV_PASS', configurations=96)
        result = dict(passed=True, exit_code=0, output='trace\nRVV_PASS cases=96 errors=0\n')
        self.assertTrue(numerical_pass(result, case))
        for output in ('echo RVV_PASS cases=96\n', 'RVV_PASS\n',
                       'RVV_PASS cases=0\n', 'RVV_PASS cases=95\n',
                       'RVV_PASS cases=96\nRVV_PASS cases=96\n'):
            with self.subTest(output=output):
                self.assertFalse(numerical_pass(dict(result, output=output), case))
        self.assertFalse(numerical_pass(dict(result, exit_code=1), case))
        self.assertFalse(numerical_pass(dict(result, passed=False), case))

    def test_legacy_case_without_declared_count(self):
        self.assertTrue(numerical_pass(
            dict(passed=True, exit_code=0, output='RVV_PASS cases=48\n'),
            dict(pass_marker='RVV_PASS')))


if __name__ == '__main__':
    unittest.main()
