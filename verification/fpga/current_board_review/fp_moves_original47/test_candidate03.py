"""Host-only contradictory/incomplete console tests; no simulation access."""
import unittest
import candidate03 as runner


class ConsoleChecks(unittest.TestCase):
    name = 'rvv_small_fp_move_restart_e16_m1_ops6'

    def text(self):
        return ('RVV_REDUCED_BEGIN cases=1\nRVV_FP_MOVE_PASS sew=16 cases=1 errors=0\n'
                f'BOARD_CASE_BEGIN {self.name}\nBOARD_CASE_PASS {self.name}\n'
                'BOARD_REPLAY_PASS\nCore Test *** SUCCESS *** (tohost = 0)\n')

    def test_valid(self):
        runner.console_check(self.text(), self.name, 16)

    def test_contradictions(self):
        for marker in ('RVV_FP_MOVE_FAIL sew=16 cases=1 errors=1', 'RVV_FP_MOVE_CAPACITY_FAIL',
                       'RVV_FP_MOVE_TRACE_DRAIN_FAILED', 'BOARD_CASE_FAIL case', 'BOARD_REPLAY_TRAP case=1',
                       'Core Test *** FAILED ***', 'Fatal: assertion failed', 'UVM_FATAL abort', 'FAILED.'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'failure-marker veto'):
                runner.console_check(self.text() + marker + '\n', self.name, 16)

    def test_incomplete(self):
        with self.assertRaises(ValueError):
            runner.console_check(self.text().replace('BOARD_REPLAY_PASS\n', ''), self.name, 16)

    def test_bad_count(self):
        with self.assertRaises(ValueError):
            runner.console_check(self.text().replace('cases=1 errors=0', 'cases=2 errors=0'), self.name, 16)

    def test_nonzero_exit(self):
        with self.assertRaises(ValueError):
            runner.console_check(self.text().replace('tohost = 0', 'tohost = 1'), self.name, 16)


if __name__ == '__main__':
    unittest.main(verbosity=2)
