import copy
import json
from pathlib import Path
import unittest
import apply_branch_combo_701 as combo


class ComboTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qc = json.loads((combo.QBS / "config.json").read_bytes())
        debug = combo.OUT / "operand-debug-1832-application-full701-20261006-01"
        cls.dc = json.loads((debug / "config.json").read_bytes())["native_config"]
        old = combo.OUT / "operand-native-static-qualification-690-20261006-01"
        static = json.loads((old / "qualification.json").read_bytes())
        cls.oc = json.loads((Path(static["native_file"]).parent / "config.json").read_bytes())
        cls.oc["qualified"] = json.loads((old / "qualified-records.json").read_bytes())["records"]
        cls.fc = json.loads((combo.FF1 / "config.json").read_bytes())
        cls.configs = dict(qbs=cls.qc, debug=cls.dc, operand=cls.oc, ff1=cls.fc)
        cls.owners = combo.scope_groups(cls.configs)
        cls.raw = dict(qbs=(combo.OUT / "qbs-pending-native448-20261006-02/first.el").read_bytes(),
                       debug=(combo.OUT / "operand-debug-branch-native1832-20261006-02/first.el").read_bytes(),
                       operand=Path(static["native_file"]).read_bytes(), ff1=(combo.FF1 / "first.el").read_bytes())

    def test_disjoint74_scopes(self):
        self.assertEqual(len(self.owners), 74)
        self.assertEqual(sum(c[1] for c in combo.COUNTS.values()), 8282)

    def test_scope_overlap_rejected(self):
        configs = copy.deepcopy(self.configs)
        scope = next(iter(configs["qbs"]["plan"]["scopes"]))
        configs["debug"]["plan"]["scopes"][scope] = {}
        with self.assertRaises(ValueError):
            combo.scope_groups(configs)

    def test_actual_native_router(self):
        split = combo.partition(b"\n".join(self.raw[g] for g in combo.GROUPS), self.owners)
        for group in combo.GROUPS:
            self.assertEqual(split[group].strip(), self.raw[group].strip())

    def test_unknown_prefix_rejected(self):
        with self.assertRaises(ValueError):
            combo.partition(b"INSTANCE: ara_tb\n" + b"\n".join(self.raw.values()), self.owners)

    def test_unknown_scope_rejected(self):
        raw = b"\n".join(self.raw.values()).replace(b"INSTANCE: ara_tb.", b"INSTANCE: other_tb.", 1)
        with self.assertRaises(ValueError):
            combo.partition(raw, self.owners)

    def test_missing_group_rejected(self):
        with self.assertRaises(ValueError):
            combo.partition(self.raw["qbs"] + self.raw["debug"], self.owners)

    def test_four_isolated_actual_bindings(self):
        for group in combo.GROUPS:
            result = combo.invoke(group, self.configs[group], self.raw[group])
            self.assertEqual(result["records"], combo.COUNTS[group][0])
            self.assertTrue(result["dependencies"])

    def test_duplicate_record_rejected_by_frozen_binder(self):
        with self.assertRaises(Exception):
            combo.invoke("qbs", self.qc, self.raw["qbs"] * 2)

    def test_no_update_or_new_exclude(self):
        text = combo.TCL.read_text()
        self.assertNotIn("-update", text)
        self.assertNotIn("gui_exclude_items", text)
        self.assertIn("set env(DVE_COVERAGE_OUTPUT) $root", text)


if __name__ == "__main__":
    unittest.main()
