#!/usr/bin/env python3
"""V-decode execution gate rejects unrelated or stale builds before artifacts."""
from pathlib import Path
import unittest
from unittest.mock import patch

import run_value_decode as r


class ValueBuildGateTest(unittest.TestCase):
    def test_wrong_metadata_rejected_early(self):
        good = dict(state='BUILT_NOT_EXECUTED', execution='NOT_RUN', post_pins_match=True,
                    trials=8, profiles=['q8_0', 'q4_0'], elements_per_trial=32768, boundary_elements=3584)
        for key, value in [('state', 'PASS'), ('execution', 'RUN'), ('post_pins_match', False),
                           ('trials', 4), ('profiles', ['q8_0']), ('elements_per_trial', 32767),
                           ('boundary_elements', 0)]:
            with self.subTest(key=key), patch.object(r.s, 'read_json', return_value=dict(good, **{key:value})), \
                    patch.object(r.s, 'digest') as digest:
                with self.assertRaises(ValueError):
                    r.checked_build(Path('/unused'))
                digest.assert_not_called()


if __name__ == '__main__':
    unittest.main()
