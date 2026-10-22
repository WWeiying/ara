import copy
import unittest
import apply_branch_combo_701_v2 as v2
import test_apply_branch_combo_701 as fixtures
from report_scope_ancestors import report_ancestors


class ActualAncestorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ComboTests.setUpClass()
        cls.groups = fixtures.ComboTests.configs

    def test_actual_701_roots_and_pure_protection(self):
        roots, names = v2.report_binding(self.groups)
        for lane in range(4):
            self.assertNotIn("ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d]" % lane, roots)
            self.assertIn("ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane" % lane, roots)
        self.assertEqual(set(roots), set(names))
        self.assertEqual(len(v2.active_scopes(self.groups)), 66)

    def test_collapsed_node_not_split(self):
        rows = [dict(Name="ara_tb", Depth="0"), dict(Name="gen_a.i_lane", Depth="1"), dict(Name="target", Depth="2")]
        self.assertEqual(report_ancestors(rows, ["ara_tb.gen_a.i_lane.target"]),
                         ["ara_tb", "ara_tb.gen_a.i_lane", "ara_tb.gen_a.i_lane.target"])
        with self.assertRaises(ValueError):
            report_ancestors(rows, ["ara_tb.gen_a"])

    def test_missing_actual_target_rejected(self):
        groups = copy.deepcopy(self.groups)
        scopes = groups["qbs"]["plan"]["scopes"]
        scopes["ara_tb.nonexistent.target"] = scopes.pop(next(iter(scopes)))
        with self.assertRaises(ValueError):
            v2.report_binding(groups)

    def test_depth_jump_duplicate_rejected(self):
        for rows in ([dict(Name="ara_tb", Depth="0"), dict(Name="target", Depth="2")],
                     [dict(Name="ara_tb", Depth="0"), dict(Name="ara_tb", Depth="0")]):
            with self.assertRaises(ValueError):
                report_ancestors(rows, ["ara_tb"])

    def test_hook_requires_bound_display_name(self):
        text = v2.TCL.read_text()
        self.assertIn("info exists combo_root_names($scope)", text)
        self.assertIn("qbsrefresh_select $scope", text)
        self.assertNotIn("-update", text)


if __name__ == "__main__":
    unittest.main()
