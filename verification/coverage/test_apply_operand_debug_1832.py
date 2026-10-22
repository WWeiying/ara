import csv
from pathlib import Path
import subprocess
import tempfile
import unittest

import apply_operand_debug_1832 as app


class ExactReportTests(unittest.TestCase):
    def write_csv(self, path, fields, rows):
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_collapsed_generate_name_stack_and_depth_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.csv"
            fields = ["Name", "Depth", "Score", "Branch", "Condition", "Line", "Toggle", "FSM"]
            row = dict.fromkeys(fields, "NA")
            rows = [dict(row, Name="ara_tb", Depth="0"), dict(row, Name="gen[0].i_lane", Depth="1"),
                    dict(row, Name="requester", Depth="2"), dict(row, Name="gen[1].i_lane", Depth="1")]
            self.write_csv(path, fields, rows)
            self.assertIn("ara_tb.gen[0].i_lane.requester", app.summaries(path))
            self.assertIn("ara_tb.gen[1].i_lane", app.summaries(path))
            rows[1]["Depth"] = "4"
            self.write_csv(path, fields, rows)
            with self.assertRaises(ValueError):
                app.summaries(path)

    def test_root_merge_requires_complete_unique_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            table, roots = Path(directory) / "table.csv", Path(directory) / "roots.csv"
            fields = ["Name", "Depth", "Score", "Branch", "Condition", "Line", "Toggle", "FSM"]
            row = dict.fromkeys(fields, "NA")
            self.write_csv(table, fields, [dict(row, Name="ara_tb", Depth="0")])
            root = {k: "NA" for k in fields if k not in ("Name", "Depth")}
            root.update(Scope="ara_tb", LocalPath="ara_tb", LocalName="ara_tb", Handle="7", Branch="50%")
            self.write_csv(roots, list(root), [root])
            self.assertEqual(app.merge_roots(table, roots, {"report_roots": ["ara_tb"]})["ara_tb"]["Branch"], "50%")
            root["LocalPath"] = "wrong"
            self.write_csv(roots, list(root), [root])
            with self.assertRaises(ValueError):
                app.merge_roots(table, roots, {"report_roots": ["ara_tb"]})

    def test_tcl_selection_contract_in_proc_source_context(self):
        hook = Path(__file__).with_name("apply_operand_debug_1832.tcl")
        script = """
set obd_library_only 1
proc load_hook {path} {global obd_library_only; source $path}
load_hook {%s}
set selected {{}}
proc gui_list_get_selected {args} {return $::selected}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::selected {{}}; return}
    if {[lsearch -exact $args -select] < 0} {error "Toggle forbidden"}
    set ::selected [list [lindex $args end]]
}
if {[obd_select_scope {ara_tb.gen[0].requester}] ne {ara_tb.gen[0].requester}} {error "Token differs"}
if {![catch {obd_token {{a b}}}]} {error "Multiple tokens accepted"}
puts PASS
""" % hook
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
