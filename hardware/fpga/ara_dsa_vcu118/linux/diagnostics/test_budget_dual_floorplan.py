import unittest

from budget_dual_floorplan import include_nested_members


class NestedBudgetTests(unittest.TestCase):
    def test_parent_accounts_for_child_and_grandchild(self):
        groups = {
            "parent": {"bounds": (1, 1, 4, 4), "members": ["fifo"]},
            "child": {"bounds": (2, 2, 3, 3), "members": ["dma"]},
            "grandchild": {"bounds": (2, 2, 2, 2), "members": ["arb"]},
        }
        include_nested_members(groups)
        self.assertEqual(groups["parent"]["budget_members"], ["arb", "dma", "fifo"])
        self.assertEqual(groups["child"]["budget_members"], ["arb", "dma"])

    def test_disjoint_and_partial_overlap_not_nested(self):
        groups = {
            "a": {"bounds": (0, 0, 1, 1), "members": ["a"]},
            "b": {"bounds": (1, 1, 2, 2), "members": ["b"]},
            "c": {"bounds": (3, 3, 4, 4), "members": ["c"]},
        }
        include_nested_members(groups)
        for name, group in groups.items():
            self.assertEqual(group["budget_members"], [name])

    def test_equal_bounds_share_capacity_without_duplicates(self):
        groups = {
            "a": {"bounds": (0, 0, 1, 1), "members": ["a", "shared"]},
            "b": {"bounds": (0, 0, 1, 1), "members": ["b", "shared"]},
        }
        include_nested_members(groups)
        for group in groups.values():
            self.assertEqual(group["budget_members"], ["a", "b", "shared"])


if __name__ == "__main__":
    unittest.main()
