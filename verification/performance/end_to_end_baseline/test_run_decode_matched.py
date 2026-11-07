import unittest
from unittest.mock import patch

import run_decode_matched as runner


class MatchedRunnerTests(unittest.TestCase):
    def test_invalid_width_rejected_before_collection(self):
        with self.assertRaises(ValueError): runner.inputs(64)

    def test_failed_predecessor_cannot_authorize_new_simulation(self):
        with patch.object(runner.Path, 'read_text', return_value='{"state":"FAIL"}'):
            with self.assertRaisesRegex(ValueError, 'Predecessor RVV gate failed'):
                runner.accepted_predecessor(128, {}, {})

    def test_mismatched_build_workload_rejected(self):
        for data in ('{"state":"FAIL"}', '{"state":"REAL_DECODE_MATCHED_ABBA_BUILT_NOT_EXECUTED",'
                     '"post_pins_match":false}'):
            with patch.object(runner, 'bind'), patch.object(runner.Path, 'read_text', return_value=data):
                with self.assertRaisesRegex(ValueError, 'Unaccepted matched build'):
                    runner.build_inputs({})

    def test_bounded_simulation_and_fresh_location(self):
        for timeout in (0, 10801):
            with self.assertRaises(ValueError): runner.run(128, runner.RUNS/'unused', timeout, False)
        with self.assertRaises(ValueError): runner.run(128, runner.Path('/tmp/unused'), 1, False)


if __name__ == '__main__': unittest.main()
