import unittest
from export_verified import select_confirmed


class SelectionTests(unittest.TestCase):
    def test_only_confirmed(self):
        m = dict(cases=[dict(name='yes', original_name='original'), dict(name='no', original_name='original')])
        p = dict(cases=[dict(name='yes', original_name='original', confirmed=True),
                        dict(name='no', original_name='original', confirmed=False)])
        self.assertEqual([c['name'] for c, _ in select_confirmed(m, p)], ['yes'])

    def test_reject_unknown_ancestor_and_duplicates(self):
        m = dict(cases=[dict(name='test', original_name='original')])
        row = dict(name='test', original_name='wrong', confirmed=True)
        with self.assertRaises(ValueError):
            select_confirmed(m, dict(cases=[row]))
        row['original_name'] = 'original'
        with self.assertRaises(ValueError):
            select_confirmed(m, dict(cases=[row, row]))
        row['confirmed'] = False
        with self.assertRaises(ValueError):
            select_confirmed(m, dict(cases=[row]))


if __name__ == '__main__':
    unittest.main()
