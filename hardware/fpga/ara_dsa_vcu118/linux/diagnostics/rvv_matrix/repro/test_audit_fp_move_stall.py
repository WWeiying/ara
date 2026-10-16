import unittest
from audit_fp_move_stall import trigger


LINE = ('RVV_MOVE_BEGIN seed=0 scalar=0 invalid_box=0 op=2 vl=32 '
        'mask=0 sticky=0 vstart=16 cap=32 completed=642')


class MoveStallTests(unittest.TestCase):
    def test_only_prior_call_count_ignored(self):
        self.assertEqual(trigger(LINE), trigger(LINE.replace('completed=642', 'completed=0')))
        self.assertNotEqual(trigger(LINE), trigger(LINE.replace('vstart=16', 'vstart=1')))

    def test_return_and_malformed_trigger_rejected(self):
        for line in ('', LINE + '\nRVV_MOVE_RETURN completed=0 status=0',
                     LINE + ' vl=32', LINE.replace('cap=32 ', ''), LINE.replace('vl=32', 'vl=x')):
            with self.assertRaises(ValueError):
                trigger(line)


if __name__ == '__main__':
    unittest.main()
