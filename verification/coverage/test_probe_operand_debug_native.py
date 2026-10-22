import csv
from pathlib import Path
import tempfile
import unittest
import probe_operand_debug_native as p


class ProbeTests(unittest.TestCase):
    def test_probe_never_excludes(self):
        text = p.TCL.read_text()
        self.assertNotIn("gui_exclude_items", text)
        self.assertNotIn("gui_list_select", text)
        self.assertIn("$p < 5", text)
        self.assertIn("$c < 6", text)
        self.assertIn("$g < 3", text)

    def test_unknown_native_names_are_evidence_not_guessed_ids(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "native.tsv"
            with path.open("w", newline="") as f:
                w = csv.writer(f, delimiter="\t")
                w.writerow(["metric", "depth", "handle", "meta", "path", "child_count", "col0", "col1", "col2", "col3"])
                w.writerow(["branch", "1", "1234", "unknownNative", "Item0.child", "0", "209", "x", "", ""])
            self.assertEqual(p.read_tree(path)[0]["meta"], "unknownNative")

    def test_duplicate_native_handle_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "native.tsv"
            path.write_text("metric\tdepth\thandle\tmeta\tpath\tchild_count\tcol0\tcol1\tcol2\tcol3\n" +
                            "branch\t1\t1234\tx\tItem0.x\t0\t\t\t\t\n" * 2)
            with self.assertRaises(ValueError):
                p.read_tree(path)


if __name__ == "__main__":
    unittest.main()
