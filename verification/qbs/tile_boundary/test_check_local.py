import unittest

from check_local import hold_gate, profile_gate


class LocalGatesTest(unittest.TestCase):
    def test_hold_requires_every_overlap_and_release(self):
        text = ('QBS_REPLAY_HOLD cycle=1 access=2\n' * 24 +
                'QBS_REPLAY_HOLD_SUMMARY holds=24 overlaps=24 held_at_end=0\n')
        self.assertEqual(hold_gate(text)['fault_overlaps'], 24)
        for changed in (text.replace('overlaps=24', 'overlaps=23'),
                        text.replace('held_at_end=0', 'held_at_end=1'), text + text):
            with self.assertRaises(ValueError):
                hold_gate(changed)

    def test_profile_exact_case_geometry_and_terminal(self):
        vectors = ''.join(f'CASE {i} 1 4 2 0\n' for i in range(448))
        rows = ''.join(f'QBS RTL case {i} PASS profile=1 M=4 rows=2 pattern=0 '
                       'first_cycles=80 repeat_cycles=82\n' for i in range(448))
        text = rows + 'QBS profile engine PASS: 448 cases\n'
        self.assertEqual(profile_gate(text, vectors)['cases'], 448)
        for changed in (text.replace('case 1 PASS', 'case 0 PASS'),
                        text.replace('M=4', 'M=3', 1), text + 'Fatal: late failure\n',
                        text.replace('first_cycles=80', 'first_cycles=0', 1)):
            with self.assertRaises(ValueError):
                profile_gate(changed, vectors)


if __name__ == '__main__':
    unittest.main()
