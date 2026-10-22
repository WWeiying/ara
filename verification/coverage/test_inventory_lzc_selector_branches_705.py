import unittest
from inventory_lzc_selector_branches_705 import structural_node
from lzc_selector_candidates import selector_expression


class SelectorBranchTests(unittest.TestCase):
    def point(self, level, index):
        return dict(line="95", expression=selector_expression(level, index),
                    attributes=dict(generate_info="level=%d,l=%d" % (level, index), totalbranches="2"))

    def test_padding_only_left_is_constant_zero(self):
        node = structural_node(self.point(2, 3), 10)
        self.assertEqual(node["reachable_selector_values"], [0])
        self.assertFalse(node["left_real_bits"])

    def test_real_left_unhit_is_not_candidate(self):
        self.assertIsNone(structural_node(self.point(0, 0), 10))

    def test_changed_expression_rejected(self):
        point = self.point(2, 3)
        point["expression"] = "different"
        with self.assertRaisesRegex(ValueError, "expression differs"):
            structural_node(point, 10)


if __name__ == "__main__":
    unittest.main()
