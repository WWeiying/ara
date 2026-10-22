import csv
from pathlib import Path
import subprocess
import tempfile
import unittest
import probe_qbs_root_refresh as probe


class RefreshTests(unittest.TestCase):
    def rows(self, mutate=None):
        scope = "ara_tb"
        rows = [dict(zip(probe.HEADER, [stage, scope, scope, "handle1", scope, scope, branch, "30.00%"]))
                for stage, branch in (("raw", "40.00%"), ("applied", "40.50%"), ("reset", "40.00%"))]
        if mutate:
            mutate(rows)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=probe.HEADER)
                writer.writeheader()
                writer.writerows(rows)
            return probe.rooted_rows(path, [scope])

    def test_exact(self):
        self.assertEqual(len(self.rows()), 3)

    def test_alias(self):
        with self.assertRaises(ValueError):
            self.rows(lambda rows: rows[1].update(Token="other.ara_tb"))

    def test_fullpath_not_local(self):
        with self.assertRaises(ValueError):
            self.rows(lambda rows: rows[1].update(GUIPath="other.ara_tb"))

    def test_reset(self):
        with self.assertRaises(ValueError):
            self.rows(lambda rows: rows[2].update(Branch="40.01%"))

    def test_missing(self):
        with self.assertRaises(ValueError):
            self.rows(lambda rows: rows.pop())

    def test_nested_selection_actual_tcl(self):
        text = probe.TCL.read_text()
        functions = text[text.index("proc qbsrefresh_tokens"):text.index("proc qbsrefresh_select")]
        script = functions + '''
if {[qbsrefresh_tokens {}] ne {}} {error empty}
if {[qbsrefresh_tokens {{ara_tb.dut}}] ne {ara_tb.dut}} {error singleton}
if {![catch {qbsrefresh_tokens {{a b}}}]} {error multiple_tokens}
if {![catch {qbsrefresh_tokens {{a} {b}}}]} {error multiple_groups}
puts PASS
'''
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), "PASS")
        self.assertEqual(result.stderr, "")

    def test_no_update(self):
        self.assertNotIn("gui_exclusion -id CoverageTable.1 -update", probe.TCL.read_text())


if __name__ == "__main__":
    unittest.main()
