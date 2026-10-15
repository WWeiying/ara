#!/usr/bin/env python3
"""Host-only negative tests; never launch a simulator."""
import json
from pathlib import Path
import unittest

import check_terminal as checker
import replay_candidate03 as replay


class Terminal(unittest.TestCase):
    def test_membership(self):
        self.assertEqual(checker.EXPECTED, replay.NAMES)
        self.assertEqual(len(checker.EXPECTED), 8)

    def test_veto_and_exact_counts(self):
        for name in checker.EXPECTED:
            sew = name.split('_')[1][1:]
            markers = [f'RVV_PERMUTE_PASS sew={sew} cases=1 errors=0',
                       'BOARD_CASE_PASS ' + name, 'BOARD_REPLAY_PASS']
            passing = '\n'.join([f'BOARD_CASE_BEGIN {name}', *markers,
                                  'Core Test *** SUCCESS *** (tohost = 0)'])
            checker.console_check(passing, name)
            self.assertTrue(replay.oracle(dict(pass_markers=markers), passing))
            for token in ('RVV_PERMUTE_FAIL', 'RVV_PERMUTE_CAPACITY_FAIL', 'RVV_PERMUTE_DETAIL',
                          'BOARD_CASE_FAIL', 'BOARD_REPLAY_TRAP', 'BOARD_REPLAY_MISMATCH',
                          'BOARD_REPLAY_VLEN_FAIL', 'BOARD_REPLAY_SERVICE_FAIL', 'SKIP',
                          'Core Test *** FAILED ***', 'UVM_FATAL : 1', 'Fatal: assertion failed'):
                with self.assertRaises(ValueError):
                    checker.console_check(passing + '\n' + token, name)
                self.assertFalse(replay.oracle(dict(pass_markers=markers), passing + '\n' + token))
            for broken in (passing.replace('cases=1 errors=0', 'cases=0 errors=0'),
                           passing.replace('errors=0', 'errors=1'),
                           passing + '\n' + markers[0],
                           passing.replace('(tohost = 0)', '(tohost = 1)'),
                           passing.replace('BOARD_CASE_BEGIN ' + name, 'BOARD_CASE_BEGIN other')):
                with self.assertRaises(ValueError):
                    checker.console_check(broken, name)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Terminal)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    (Path(__file__).parent / 'checker_host.json').write_text(json.dumps(
        dict(status='PASS' if result.wasSuccessful() else 'FAIL', tests=result.testsRun,
             worker_sha256=replay.sha(Path(replay.__file__)),
             checker_sha256=replay.sha(Path(checker.__file__))), indent=2) + '\n')
    raise SystemExit(not result.wasSuccessful())
