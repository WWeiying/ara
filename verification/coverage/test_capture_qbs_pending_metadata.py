import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import capture_qbs_pending_metadata as m


class QBSPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(m.INVENTORY.read_bytes())
        cls.bitmap = json.loads((m.BASE / "combined-bits.json").read_bytes())
        cls.design = m.native.inventory.Design(Path(json.loads(m.native.PLAN.read_bytes())["design_vdb"]))
        cls.pilot = m.build_scopes(cls.design, cls.bitmap, cls.inventory, "pilot")
        cls.full = m.build_scopes(cls.design, cls.bitmap, cls.inventory, "full")

    def fixture(self):
        config = dict(plan=dict(scopes=copy.deepcopy(self.pilot)))
        lines = []
        for scope, metrics in config["plan"]["scopes"].items():
            rows = [r for r in metrics["branch"] if r["target"]]
            self.assertEqual(len(rows), 1)
            r, p = rows[0], rows[0]["point"]
            lines += ['CHECKSUM: "%s %s"' % (r["module_checksum"], r["metric_checksum"]), "INSTANCE: " + scope,
                'ANNOTATION: "vcs_gen_start:' + p["attributes"]["generate_info"] + ':vcs_gen_end:' + m.ANNOTATION + '"',
                'Branch %s "%s" "%s" (%s) "%s 1,0"' % (p["native_id"], p["attributes"]["chksum"],
                    p["expressions"][0]["exprstr"], p["vector"], p["expressions"][1]["exprstr"])]
        return ("\n".join(lines) + "\n").encode(), config

    def test_pilot_exact_two_banks_with_four_neighbors(self):
        rows = [r for s in self.pilot.values() for r in s["branch"]]
        self.assertEqual(len(rows), 4238)
        self.assertEqual(sum(r["target"] for r in rows), 2)
        self.assertEqual(sum(r["audit"] for r in rows), 6)
        self.assertEqual(sum(r["audit"] and not r["target"] for r in rows), 4)

    def test_full_exact448_all_functional_neighbors_audited(self):
        rows = [r for s in self.full.values() for r in s["branch"]]
        self.assertEqual(sum(r["target"] for r in rows), 448)
        self.assertTrue(all(r["audit"] for r in rows))
        self.assertEqual(sum(not r["target"] for r in rows), 3790)
        self.assertFalse(any(r["target"] and r["point"]["line"] == "285" for r in rows))

    def test_exact_compiled_native_fixture(self):
        raw, config = self.fixture()
        self.assertEqual(len(m.bind_native(raw, config)), 2)

    def test_wrong_generate_annotation_rejected(self):
        raw, config = self.fixture()
        with self.assertRaises(ValueError):
            m.bind_native(raw.replace(b"row=0,b=0", b"row=1,b=0", 1), config)

    def test_wrong_source_expression_rejected(self):
        raw, config = self.fixture()
        with self.assertRaises(ValueError):
            m.bind_native(raw.replace(b".enable", b".other", 1), config)

    def test_duplicate_and_extra_record_rejected(self):
        raw, config = self.fixture()
        for changed in (raw + raw, raw + b'Toggle 1 "0" "x"\n'):
            with self.assertRaises(ValueError):
                m.bind_native(changed, config)

    def test_newer_cannot_be_target(self):
        raw, config = self.fixture()
        for metrics in config["plan"]["scopes"].values():
            for row in metrics["branch"]:
                if row["target"]:
                    row["point"]["native_vector"] = {"id": "0", "vector": "0011"}
                    break
            break
        with self.assertRaises(ValueError):
            m.bind_native(raw, config)

    def test_inventory_mutation_rejected(self):
        inv = copy.deepcopy(self.inventory)
        inv["points"][0]["point"]["raw_index"] += 1
        with self.assertRaises(ValueError):
            m.build_scopes(self.design, self.bitmap, inv, "pilot")

    def test_protected_singleton_rejects_any_boolean_exclusion(self):
        c = dict(plan=dict(scopes=self.pilot))
        rows = ["scope\tmetric\tcoordinate\tmeta\tpath\texcluded"]
        for scope, metrics in self.pilot.items():
            for r in metrics["branch"]:
                if r["audit"]:
                    sid, vid = r["coordinate"].split(",")
                    meta = "Branch%s.%s" % (sid, vid)
                    rows.append("\t".join((scope, "branch", r["coordinate"], meta, "Item" + sid + "." + meta,
                        "1" if r["target"] else "0")))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "states.tsv"
            path.write_text("\n".join(rows) + "\n")
            self.assertEqual(len(m.audit_states(path, c, "selected")), 6)
            i = next(i for i, r in enumerate(rows[1:], 1) if r.endswith("\t0"))
            rows[i] = rows[i][:-1] + "1"
            path.write_text("\n".join(rows) + "\n")
            with self.assertRaises(ValueError):
                m.audit_states(path, c, "selected")

    def test_tcl_session_selection_arrays_global_before_gui(self):
        prelude = m.TCL.read_text().split("set failed [catch {qbs_session} message]", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            sample = out / "sample.vdb"
            (sample / "snps/coverage/db/testdata/one").mkdir(parents=True)
            plan = dict(scopes=self.pilot, design_vdb="unused.vdb", selected_test_vdb=str(sample))
            script = m.native.selection(plan)
            for name, audit_only in (("qbs_native_keys", False), ("qbs_audit_keys", True)):
                script += "array set " + name + " {\n" + "\n".join(m.capture.literal(s) + " {" +
                    " ".join(r["coordinate"] for r in metrics["branch"] if not audit_only or r["audit"])
                    + "}" for s, metrics in self.pilot.items()) + "\n}\n"
            (out / "selection.tcl").write_text(script)
            (out / "live-ready").write_text("MOCK_ONLY\n")
            script = prelude + '''
set env(DVE_COVERAGE_OUTPUT) {%s}
proc gui_open_cov {args} {
    global qbs_native_keys qbs_audit_keys dbg_scopes dbg_targets
    foreach s $dbg_scopes {
        if {[llength $qbs_native_keys($s)] != 2119 || [llength $qbs_audit_keys($s)] != 3 ||
            [llength $dbg_targets($s|branch)] != 1} {error WRONG_SELECTION}
    }
    set ::mock_pass 1
    error STOP_BEFORE_GUI
}
catch {qbs_session} message
if {![info exists mock_pass] || $message ne "STOP_BEFORE_GUI"} {error $message}
puts PASS
''' % directory
            result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
