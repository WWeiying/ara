import unittest
from batch_fault_singles import select


class SelectionTests(unittest.TestCase):
    def group(self, name, match=True):
        return name, dict(cases=[dict(aggregate_original_symptom_matches=match) for _ in range(3)])

    def test_selected_only_after_three_way_agreement(self):
        self.assertEqual(select([self.group('a'), self.group('b')], ['a']), ['b'])

    def test_reject_incomplete_duplicate_unknown_or_empty(self):
        for groups, excluded in (([self.group('a', False)], []),
                                 ([self.group('a'), self.group('a')], []),
                                 ([self.group('a')], ['b']),
                                 ([self.group('a')], ['a']),
                                 ([('a', dict(cases=[]))], []),
                                 ([self.group('../escape')], [])):
            with self.subTest(groups=groups, excluded=excluded):
                with self.assertRaises(ValueError):
                    select(groups, excluded)


if __name__ == '__main__':
    unittest.main()
