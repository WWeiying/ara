import copy
import csv
from pathlib import Path
import tempfile
import unittest

import apply_qbs_historical_v2 as m


class DisplayHierarchyTests(unittest.TestCase):
    fields = ["Name", "Depth", "GUIPath", "Scope", "Score", "Line", "Toggle", "FSM", "Condition", "Branch"]

    def fixture(self):
        paths = [("ara_tb", 0, "ara_tb"), ("dut", 1, "ara_tb.dut"),
            ("i_ara_soc", 2, "ara_tb.dut.i_ara_soc"), ("i_system", 3, "ara_tb.dut.i_ara_soc.i_system"),
            ("gen_x.i_block", 4, "ara_tb.dut.i_ara_soc.i_system.gen_x.i_block"),
            ("i_child", 5, "ara_tb.dut.i_ara_soc.i_system.gen_x.i_block.i_child")]
        return [dict(zip(self.fields, [name, str(depth), path, path, "80%", "80%", "80%", "60%", "80%", "80%"]))
                for name, depth, path in paths]

    def parse(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.csv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=self.fields)
                writer.writeheader()
                writer.writerows(rows)
            return m.summary(path)

    def test_collapsed_name_is_one_display_depth(self):
        rows = self.fixture()
        parsed = self.parse(rows)
        self.assertEqual(len(parsed), 6)
        self.assertIn(rows[-1]["GUIPath"], parsed)

    def test_depth_jump_rejected(self):
        rows = self.fixture()
        rows[-1]["Depth"] = "7"
        with self.assertRaisesRegex(ValueError, "depth jump"):
            self.parse(rows)

    def test_wrong_parent_gui_path_rejected(self):
        rows = self.fixture()
        rows[-1]["GUIPath"] = rows[-1]["Scope"] = "ara_tb.dut.i_ara_soc.i_system.i_child"
        with self.assertRaisesRegex(ValueError, "display hierarchy"):
            self.parse(rows)

    def test_collapsed_alias_duplicate_rejected(self):
        rows = self.fixture()
        alias = copy.deepcopy(rows[-2])
        alias["Name"] = "i_block"
        alias["Depth"] = "5"
        parent = copy.deepcopy(rows[-2])
        parent["Name"] = "gen_x"
        parent["GUIPath"] = parent["Scope"] = "ara_tb.dut.i_ara_soc.i_system.gen_x"
        with self.assertRaisesRegex(ValueError, "aliased"):
            self.parse(rows + [parent, alias])

    def test_empty_scope_component_rejected(self):
        rows = self.fixture()
        rows[-2]["Name"] = "gen_x..i_block"
        with self.assertRaisesRegex(ValueError, "display name"):
            self.parse(rows)

    def test_relative_root_rejected(self):
        rows = self.fixture()
        rows[0]["Name"] = "i_system"
        with self.assertRaises(ValueError):
            self.parse(rows)

    def test_partial_csv_rejected(self):
        rows = self.fixture()
        del rows[-1]["Branch"]
        with self.assertRaisesRegex(ValueError, "Partial CSV"):
            self.parse(rows)

    def test_actual_all_three_summaries(self):
        reports = [m.summary(m.FAILED / ("summary_%s.csv" % stage)) for stage in ("raw", "applied", "reset")]
        self.assertEqual([len(r) for r in reports], [2988, 2988, 2988])
        self.assertEqual(reports[0], reports[2])
        self.assertEqual(set(reports[0]), set(reports[1]))


if __name__ == "__main__":
    unittest.main()
