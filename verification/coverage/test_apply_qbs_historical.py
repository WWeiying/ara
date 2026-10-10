import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import apply_qbs_historical as m


class ApplicationPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qc = json.loads((m.QUALIFIED / "config.json").read_bytes())
        cls.bitmap = json.loads((m.BASE / "combined-bits.json").read_bytes())

    def test_actual699_target_zero_protected3790(self):
        scopes = m.latest_scopes(self.qc, self.bitmap)
        self.assertEqual(sum(r["target"] for s in scopes.values() for r in s["branch"]), 448)
        self.assertEqual(sum(not r["target"] for s in scopes.values() for r in s["branch"]), 3790)

    def test_newest_hit_rejects_waiver(self):
        bitmap = copy.deepcopy(self.bitmap)
        scope = next(iter(self.qc["plan"]["scopes"]))
        point = next(r["point"] for r in self.qc["plan"]["scopes"][scope]["branch"] if r["target"])
        rec = bitmap["metrics"]["branch"][scope]
        rec["bits"] = format(int(rec["bits"], 16) | (1 << (rec["width"] - point["raw_index"] - 1)), "x")
        with self.assertRaisesRegex(ValueError, "contradicts"):
            m.latest_scopes(self.qc, bitmap)

    def test_future700_not_accepted(self):
        bitmap = copy.deepcopy(self.bitmap)
        bitmap["tests"].append("unverified700")
        with self.assertRaises(ValueError):
            m.latest_scopes(self.qc, bitmap)

    def test_foreign_shape_rejected(self):
        bitmap = copy.deepcopy(self.bitmap)
        bitmap["design"] = {}
        with self.assertRaises(ValueError):
            m.latest_scopes(self.qc, bitmap)

    def test_exact699_gui_membership(self):
        inputs = (m.BASE / "combined-inputs.txt").read_text().splitlines()
        names = m.selected(inputs, self.bitmap, self.qc["plan"]["design_vdb"])
        self.assertEqual(len(names), 699)
        self.assertEqual(names, (m.RAW / "selected_tests.txt").read_text().splitlines())
        with self.assertRaises(ValueError):
            m.selected(inputs[:-1] + inputs[1:2], self.bitmap, inputs[0])

    def test_summary_rejects_relative_root_path(self):
        fields = ["Name", "Depth", "GUIPath", "Scope", "Score", "Line", "Toggle", "FSM", "Condition", "Branch"]
        rows = [dict(zip(fields, ["ara_tb", "0", "ara_tb", "ara_tb", "80%", "80%", "80%", "60%", "80%", "80%"])),
            dict(zip(fields, ["i_system", "3", "ara_tb.dut.i_ara_soc.i_system", "ara_tb.dut.i_ara_soc.i_system", "80%", "80%", "80%", "60%", "80%", "80%"]))]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "summary.csv"
            def save():
                with path.open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=fields)
                    w.writeheader()
                    w.writerows(rows)
            save()
            self.assertEqual(len(m.summary(path)), 2)
            rows[1]["GUIPath"] = "i_system"
            save()
            with self.assertRaises(ValueError):
                m.summary(path)

    def test_only_exact_append_only_historical_document_is_recovered(self):
        original = b"Original review\n"
        expected = hashlib.sha256(original).hexdigest()
        suffix = "\n## 完整原生资格核验结果\nNew note\n".encode("utf-8")
        self.assertEqual(m.historical_review(original + suffix, expected), original)
        for raw in (original.replace(b"review", b"changed") + suffix, original + b"\nunknown appendix\n"):
            with self.assertRaises(ValueError):
                m.historical_review(raw, expected)


if __name__ == "__main__":
    unittest.main()
