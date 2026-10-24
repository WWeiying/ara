#!/usr/bin/env python3
"""A live/failed QK inquiry must never authorize downstream execution."""
from pathlib import Path
import unittest
from unittest.mock import patch

import run_attention as r


class PrerequisiteTest(unittest.TestCase):
    def test_nonterminal_or_unchecked_gate_rejected(self):
        status = dict(state='PASS', child_pid=None)
        result = dict(state='PASS', post_pins_match=True, simulator_exit_code=0)
        for key, value, target in [('state', 'RUNNING', 'status'), ('state', 'FAIL', 'result'),
                                   ('child_pid', 1234, 'status'), ('post_pins_match', False, 'result'),
                                   ('simulator_exit_code', 1, 'result')]:
            a, b = dict(status), dict(result)
            (a if target == 'status' else b)[key] = value
            with self.subTest(key=key, target=target), patch.object(r.s, 'read_json', side_effect=[a, b]), \
                    patch.object(r, 'prepare_batch') as prepare:
                with self.assertRaises(ValueError):
                    r.checked_prerequisite(Path('/unused'))
                prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
