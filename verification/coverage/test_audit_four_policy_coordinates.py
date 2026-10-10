import unittest

from audit_four_policy_coordinates import check_disjoint, targets_from_plan


class CoordinateAuditTests(unittest.TestCase):
    def test_disjoint_and_overlap(self):
        check_disjoint({'a': {('x', 0)}, 'b': {('x', 1)}})
        with self.assertRaises(ValueError):
            check_disjoint({'a': {('x', 0)}, 'b': {('x', 0)}})

    def test_targets_only_and_duplicate_rejection(self):
        target = dict(target=True, point=dict(raw_index=2))
        protected = dict(target=False, point=dict(raw_index=3))
        config = dict(plan=dict(scopes={'x': dict(branch=[target, protected])}))
        self.assertEqual(targets_from_plan(config), {('x', 2)})
        config['plan']['scopes']['x']['branch'].append(target)
        with self.assertRaises(ValueError):
            targets_from_plan(config)


if __name__ == '__main__':
    unittest.main()
