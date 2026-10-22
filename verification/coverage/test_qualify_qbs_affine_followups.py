import unittest
from unittest.mock import patch
from pathlib import Path

import qualify_qbs_affine_followups as follow


class Followups(unittest.TestCase):
    def test_exact_terminal_cases(self):
        self.assertEqual(set(follow.CASES), {'scale', 'min_scale'})
        self.assertEqual(len({value[1] for value in follow.CASES.values()}), 2)
        for name, seal in follow.CASES.values():
            self.assertTrue(name.endswith('agent-20261007-01'))
            self.assertEqual(len(seal), 64)

    def test_unknown_stage_never_calls_collector(self):
        with patch.object(follow.closure, 'source_pins', return_value={}), \
             patch.object(follow.q.life, 'digest', return_value='0' * 64), \
             patch.object(follow, 'FunctionType') as fn:
            with self.assertRaises(KeyError):
                follow.collect('aux', Path('/unused'))
            fn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
