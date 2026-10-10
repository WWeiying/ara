import unittest
import admit_targeted_toggle741 as tool


class Admission(unittest.TestCase):
    def test_exact_prefix(self):
        before = [str(i) for i in range(740)]
        tool.exact_prefix(before, ['design'] + before)
        for ledger in (['design'] + before[::-1], ['design'] + before[:-1]):
            with self.assertRaises(ValueError):
                tool.exact_prefix(before, ledger)

    def test_duplicate_and_candidate_rejected(self):
        before = [str(i) for i in range(740)]
        before[-1] = before[0]
        with self.assertRaises(ValueError):
            tool.exact_prefix(before, ['design'] + before)
        before = [str(i) for i in range(739)] + [str(tool.VDB)]
        with self.assertRaises(ValueError):
            tool.exact_prefix(before, ['design'] + before)

    def test_toggle_not_assumed_from_other_metrics(self):
        old = dict(tests=list(range(740)), metrics={'s': dict(width=4, checksum='7', bits='0x4')})
        changes, gain = tool.toggle_gain(old, {'s': dict(width=4, checksum='7', bits='0x9')})
        self.assertEqual((changes, gain), ({'s': [0, 3]}, 2))
        self.assertEqual(tool.toggle_gain(old, old['metrics']), ({'s': []}, 0))
        with self.assertRaises(ValueError):
            tool.toggle_gain(old, {'s': dict(width=5, checksum='7', bits='0x9')})


if __name__ == '__main__':
    unittest.main()
