#!/usr/bin/env python3
"""Reject stale-runtime builds and retain both strict transcript checkers."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_live_regression as r


class GateTest(unittest.TestCase):
    def test_reject_wrong_build_before_reading_artifacts(self):
        good = dict(kind='decode', state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
                    post_pins_match=True, old_runtime_objects_reused=False,
                    expected_commands=3680, expected_calls=12)
        for key, value in [('kind', 'prefill'), ('state', 'PASS'), ('execution', 'RUN'),
                           ('post_pins_match', False), ('old_runtime_objects_reused', True),
                           ('expected_commands', 3679), ('expected_calls', 11)]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                bad = dict(good, **{key: value})
                with patch.object(r.s, 'read_json', return_value=bad), patch.object(r.s, 'digest') as digest:
                    with self.assertRaises(ValueError):
                        r.checked_build(Path(tmp), 'decode')
                    digest.assert_not_called()

    def test_reject_incomplete_raw_evidence(self):
        for kind in ('decode', 'prefill'):
            for text in ('', 'Core Test Passed', 'UVM_ERROR : 0\nUVM_FATAL : 0\n'):
                with self.subTest(kind=kind, text=text), self.assertRaises(ValueError):
                    r.checker(kind)(text)


if __name__ == '__main__':
    unittest.main()
