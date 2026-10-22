"""Offline synthetic EL/CSV fixtures and Tcl command mocks; no DVE or EDA."""
import copy
import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_lzc_batch as b


def fixture_bound():
    candidates, retained = [], []
    for i in range(120):
        table = dict(ncols="2", nrows="3", vecs="000110")
        base = dict(scope="dut.lzc%d" % i, expression="(left[%d] | right[%d])" % (i, i),
                    module="lzc", metric="cond", native_id=str(i + 1), metric_checksum="20",
                    attributes=dict(chksum=str(300 + i), width="1"), truth_table=table, line="93")
        for vector in (["01", "10"] if i < 60 else ["01"]):
            candidates.append(dict(module_checksum="10", point=dict(base, vector=vector),
                structural_proof=dict(unreachable_child_vectors=["01", "10", "11"])))
        if i < 22:
            retained.append(dict(point=dict(base, vector="00")))
        selector = dict(base, expression="(left[%d] == 1'b1)" % i, line="95",
                        truth_table=dict(ncols="1", nrows="2", vecs="01"), vector="1")
        retained.append(dict(point=selector))
    return dict(candidates=candidates, retained=retained, candidate_count=180, retained_count=142)


def native_text(bound):
    lines = []
    for c in bound["candidates"]:
        p = c["point"]
        # Deliberately not the XML row ordering: 01 is ID2, 10 is ID1.
        vector_id = {"01": "2", "10": "1"}[p["vector"]]
        lines.extend(['CHECKSUM: "%s %s"' % (c["module_checksum"], p["metric_checksum"]),
                      "INSTANCE: " + p["scope"],
                      'Condition %s "%s" "%s 1 -1" (%s "%s")' %
                      (p["native_id"], p["attributes"]["chksum"], p["expression"], vector_id, p["vector"])])
    return "\n".join(lines) + "\n"


class GroupTests(unittest.TestCase):
    def test_exact180_names_grouped_native_or_only_retained_inventory_preserved(self):
        bound = fixture_bound()
        rows = b.groups(bound)
        self.assertEqual(len(rows), 120)
        self.assertEqual(sum(len(r["targets"]) for r in rows), 180)
        keep = {(r["scope"], r["expression"], v) for r in rows for v in r["retained"]}
        self.assertEqual(len(bound["retained"]), 142)
        self.assertTrue({b.key(r["point"]) for r in bound["retained"] if r["point"]["line"] == "93"} <= keep)
        self.assertTrue(all("==" not in r["expression"] and r["targets"] for r in rows))
        self.assertTrue(any(r["targets"] == ["01", "10"] and r["retained"] == ["00"] for r in rows))

    def test_missing_duplicate_overlap_unknown_vector_and_unproved_reject(self):
        original = fixture_bound()
        variants = []
        changed = copy.deepcopy(original)
        changed["candidates"].pop()
        variants.append(changed)
        changed = copy.deepcopy(original)
        changed["candidates"][1] = copy.deepcopy(changed["candidates"][0])
        variants.append(changed)
        changed = copy.deepcopy(original)
        changed["retained"][0]["point"] = copy.deepcopy(changed["candidates"][0]["point"])
        variants.append(changed)
        changed = copy.deepcopy(original)
        changed["candidates"][0]["point"]["vector"] = "1"
        variants.append(changed)
        changed = copy.deepcopy(original)
        changed["candidates"][0]["structural_proof"]["unreachable_child_vectors"] = []
        variants.append(changed)
        for i, bound in enumerate(variants):
            with self.subTest(i=i), self.assertRaises(ValueError):
                b.groups(bound)

    def test_real_bound_file_offline_population(self):
        bound = json.loads(b.CANDIDATES.read_text())
        original = copy.deepcopy(bound)
        rows = b.groups(bound)
        self.assertEqual(len(bound["tests"]), 687)
        self.assertEqual(sum(len(g["targets"]) for g in rows), 180)
        keep = {(g["scope"], g["expression"], v) for g in rows for v in g["retained"]}
        coords = {(g["scope"], g["expression"]) for g in rows}
        self.assertTrue({b.key(c["point"]) for c in bound["retained"]
                         if (c["point"]["scope"], c["point"]["expression"]) in coords} <= keep)
        self.assertEqual(bound, original)
        self.assertEqual(len(bound["retained"]), 142)
        self.assertEqual(len(rows), 120)

    def test_fresh_output_and_selection_build_never_admits_or_runs_process(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, "Fresh"):
            b.prepare(Path(tmp))
        with patch.object(b.admission.Adapter, "admit", side_effect=AssertionError("full check")), \
             patch.object(b.subprocess, "run", side_effect=AssertionError("EDA")):
            b.groups(fixture_bound())

    def test_real_shape_and_structural_proof_recompute_matches_all180_and142(self):
        with patch.object(b.admission.Adapter, "admit", side_effect=AssertionError("full check")), \
             patch.object(b.subprocess, "run", side_effect=AssertionError("EDA")):
            bound = json.loads(b.CANDIDATES.read_text())
            bitmap = json.loads((b.BASELINE / "combined-bits.json").read_text())
            inventory = json.loads((b.OUT / "closure90-zero-inventory-654-20261005-01/inventory.json").read_text())
            plan = json.loads((b.admission.old.CURRENT / "plan.json").read_text())
            bindings = b.shape.shape_bindings(inventory["source_points"], bitmap,
                                              Path(plan["design_vdb"]) / "snps/coverage/db")
            result = b.shape.classify(inventory["source_points"], bitmap, bindings)
            self.assertEqual(result["candidates"], bound["candidates"])
            self.assertEqual(result["retained"], bound["retained"])


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lzc-batch-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "capture"
        self.output.mkdir()
        self.bound = fixture_bound()
        self.rows = b.groups(self.bound)
        self.sample = self.root / "code.vdb"
        (self.sample / "snps/coverage/db/testdata/vgap79_add16").mkdir(parents=True)
        for name in ("first.el", "second.el"):
            (self.output / name).write_text(native_text(self.bound))
        for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
            (self.output / name).write_text("")
        (self.output / "DVEfiles").mkdir()
        (self.output / "DVEfiles/dve_gui.log").write_text("LZC_BATCH_CAPTURE_DONE 180\nDVE_COVERAGE_EXPORT_DONE\n")
        (self.output / "selected_tests.txt").write_text(str(self.sample.with_suffix("") / "vgap79_add16") + "\n")
        (self.output / "summary.csv.partial").write_text("raw sample only\n")
        self.write_audit()

    def write_audit(self):
        self.audit = []
        for stage in b.STAGES:
            for g in self.rows:
                self.audit.append([stage, g["scope"], g["expression"], " ".join(g["names"]),
                    " ".join(g["targets"]), " ".join(g["retained"]),
                    str(len(g["targets"]) if stage in ("selected", "reloaded") else 0), "0"])
        with (self.output / "neighbor-audit.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(b.AUDIT_COLUMNS)
            writer.writerows(self.audit)

    def verify(self):
        return b.verify_artifacts(self.output, self.bound, self.rows, str(self.sample))

    def test_first_second180_threeempty_neighbors_and_captured_id(self):
        result = self.verify()
        self.assertEqual(result["candidate_count"], 180)
        self.assertEqual(result["captured_tests"], 1)
        self.assertFalse(result["native_qualified"])
        self.assertFalse(result["application_approval"])
        self.assertTrue(result["final_reset"])
        self.assertEqual(result["retained_inventory_count"], 142)
        self.assertEqual(result["native_neighbor_audit"]["expressions"], 120)
        self.assertEqual(result["native_neighbor_audit"]["retained_vectors"], 180)
        self.assertFalse(result["native_neighbor_audit"]["covers_full_retained_inventory"])
        self.assertEqual({r["vector_id"] for r in result["captured_vector_ids"] if r["vector"] == "01"}, {"2"})

    def test_whole_condition_wrong_signature_extra_missing_and_id_drift_reject(self):
        original = native_text(self.bound)
        variants = [original.replace('(2 "01")', '', 1), original.replace('Condition 1 "300"', 'Condition 1 "999"', 1),
                    original + original, "\n".join(original.splitlines()[:-3]),
                    original.replace('(2 "01")', '(9 "01")', 1)]
        for i, text in enumerate(variants):
            with self.subTest(i=i):
                (self.output / "second.el").write_text(text)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_each_empty_must_parse_and_bind_zero(self):
        for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
            with self.subTest(name=name):
                (self.output / name).write_text(native_text(self.bound))
                with self.assertRaises(ValueError):
                    self.verify()
                (self.output / name).write_text('CHECKSUM: "1 2"\nINSTANCE: whole.scope\n')
                with self.assertRaises(ValueError):
                    self.verify()
                (self.output / name).write_text("")

    def test_extra_retained_selector_record_rejected_despite_no_native_selector_query(self):
        p = next(c["point"] for c in self.bound["retained"] if c["point"]["line"] == "95")
        extra = ('CHECKSUM: "10 20"\nINSTANCE: %s\nCondition %s "%s" "%s 1 -1" (1 "1")\n' %
                 (p["scope"], p["native_id"], p["attributes"]["chksum"], p["expression"]))
        for filename in ("first.el", "second.el"):
            with self.subTest(filename=filename):
                (self.output / filename).write_text(native_text(self.bound) + extra)
                with self.assertRaisesRegex(ValueError, "population"):
                    self.verify()
                (self.output / filename).write_text(native_text(self.bound))

    def test_missing_neighbor_audit_and_excluded_retained_reject(self):
        p = self.output / "neighbor-audit.csv"
        original = p.read_text()
        for text in ("\n".join(original.splitlines()[:-1]), original.replace(',0,0', ',0,1', 1)):
            p.write_text(text)
            with self.assertRaisesRegex(ValueError, "audit"):
                self.verify()

    def test_full_population_and_completion_errors_reject(self):
        p = self.output / "selected_tests.txt"
        original = p.read_text()
        p.write_text(original * 687)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.verify()
        p.write_text(original)
        log = self.output / "DVEfiles/dve_gui.log"
        original = log.read_text()
        for text in ("", original + "DVE_COVERAGE_EXPORT_DONE\n", original + "Error: bad export\n"):
            log.write_text(text)
            with self.assertRaisesRegex(ValueError, "completion"):
                self.verify()


TCL_MOCK = r'''
set scope ""
set expression ""
set cond_selected {}
set vector_selected {}
set resets 0
set excludes 0
set fail_exclude 0
set missing_target 0
set wrong_names 0
set stuck 0
array set excluded {}
proc csv_row {stream values} {
    set quoted {}
    foreach value $values {lappend quoted "\"[string map [list \" \"\"] $value]\""}
    puts $stream [join $quoted ,]
}
proc arg {args flag} {
    set at [lsearch -exact $args $flag]
    if {$at < 0} {error "Missing option $flag"}
    return [lindex $args [expr {$at + 1}]]
}
proc gui_list_action {args} {global scope; set scope [lindex $args end]}
proc gui_covdetail_query {args} {return Condition}
proc gui_list_get_selected {args} {
    global scope expression cond_selected vector_selected lzc_batch_groups wrong_names
    set kind [arg $args -list]
    if {$kind eq "cond"} {set chosen $cond_selected} else {set chosen $vector_selected}
    if {[lsearch -exact $args -count] >= 0} {return [llength $chosen]}
    if {[lsearch -exact $args -first] >= 0} {
        if {![llength $chosen]} {error "Empty first query"}
        return [list [list [lindex $chosen 0]]]
    }
    if {[lsearch -exact $args -all] >= 0} {
        foreach group $lzc_batch_groups {
            if {[lindex $group 0] eq $scope && [lindex $group 1] eq $expression} {
                if {$wrong_names} {return {00 1 10}}
                return [lindex $group 2]
            }
        }
        error "Unknown point"
    }
    if {[lsearch -exact $args -flat] >= 0} {return $chosen}
    error "Unsupported query"
}
proc gui_list_select {args} {
    global cond_selected vector_selected expression stuck
    set kind [arg $args -list]
    if {[lsearch -exact $args -unselect] >= 0} {
        if {!$stuck} {
            if {$kind eq "cond"} {set cond_selected {}} else {set vector_selected [lrange $vector_selected 1 end]}
        }
    } else {
        set names [arg $args -select]
        if {$kind eq "cond"} {
            set expression [lindex $names 0]
            if {[string first "==" $expression] >= 0} {error "XML selector must never be queried natively"}
            set cond_selected $names
            set vector_selected {}
        }
        if {$kind eq "vector"} {set vector_selected $names}
    }
}
proc gui_exclude_items {args} {
    global scope expression vector_selected excluded excludes fail_exclude missing_target
    if {[lsearch -exact $args -vector] >= 0 || [arg $args -list] ne "vector" ||
        [lsearch -exact $args -selected] < 0} {error "Wrong exclusion API"}
    incr excludes
    if {$fail_exclude && $excludes == 2} {error "Injected capture failure"}
    foreach vector $vector_selected {
        if {$missing_target && $vector eq "10"} {continue}
        set excluded($scope,$expression,$vector) 1
    }
}
proc gui_exclusion {args} {
    global scope expression vector_selected excluded resets
    if {[lsearch -exact $args -reset] >= 0} {
        incr resets
        array unset excluded
        array set excluded {}
        return
    }
    if {[lsearch -exact $args -recalculate] >= 0} {return}
    # The real API is allowed to be any-selected boolean, NOT a count.
    foreach vector $vector_selected {if {[info exists excluded($scope,$expression,$vector)]} {return 1}}
    return 0
}
proc gui_exclusion_file {args} {
    global env excluded native_text lzc_batch_groups
    set path [lindex [arg $args -file] 0]
    if {[lsearch -exact $args -save] >= 0} {
        set out [open $path w]
        if {[array size excluded]} {puts -nonewline $out $native_text}
        close $out
    } else {
        foreach group $lzc_batch_groups {
            foreach vector [lindex $group 3] {set excluded([lindex $group 0],[lindex $group 1],$vector) 1}
        }
    }
}
proc gui_cov_excl_review {args} {return 1}
'''


@unittest.skipUnless(shutil.which("tclsh"), "tclsh required for offline Tcl mocks")
class TclTests(unittest.TestCase):
    def run_tcl(self, body, output, bound):
        script = "source %s\n" % b.tcl_word(b.TCL)
        script += TCL_MOCK
        script += '\nset env(DVE_COVERAGE_OUTPUT) %s\n' % b.tcl_word(output)
        script += 'set native_text %s\n' % b.tcl_word(native_text(bound))
        script += '\nif {[catch {\n' + body + '\n} message]} {puts stderr $message; exit 1}\nputs CASE_PASS\n'
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CASE_PASS", result.stdout)
        return result.stdout

    def test_full180_roundtrip_neighbors_and_finalreset(self):
        bound = fixture_bound()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "groups.tcl").write_text(b.group_script(b.groups(bound)))
            text = self.run_tcl('apply_reviewed_waivers CoverageTable.1\n'
                'if {$resets != 2 || [array size excluded] != 0 || $excludes != 120} {error "Wrong lifecycle"}', output, bound)
            self.assertIn("LZC_BATCH_CAPTURE_DONE 180", text)
            first = b.parse_records((output / "first.el").read_text())
            b.bind_records(first, bound["candidates"])
            self.assertEqual(first, b.parse_records((output / "second.el").read_text()))
            for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
                b.bind_records(b.parse_records((output / name).read_text()), [])
            with (output / "neighbor-audit.csv").open(newline="") as stream:
                audit = list(csv.DictReader(stream))
            self.assertEqual(len(audit), len(b.groups(bound)) * 5)
            self.assertTrue(all(row["RetainedExcluded"] == "0" for row in audit))
            two_target = [row for row in audit if row["Targets"] == "01 10"]
            self.assertEqual(len(two_target), 60 * 5)
            self.assertTrue(all(row["TargetExcluded"] == ("2" if row["Stage"] in ("selected", "reloaded") else "0")
                                for row in two_target))

    def test_two_targets_any_boolean_query_cannot_hide_missing10(self):
        bound = fixture_bound()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "groups.tcl").write_text(b.group_script(b.groups(bound)))
            text = self.run_tcl('set missing_target 1\nset failed [catch {apply_reviewed_waivers CoverageTable.1} msg]\n'
                'if {!$failed || $msg ne "Target exclusion state differs/nonboolean state" || '
                '$resets != 1 || [array size excluded]} {error "Missing single-vector check"}', output, bound)
            self.assertNotIn("LZC_BATCH_CAPTURE_DONE", text)
            self.assertEqual(b.parse_records((output / "final-empty.el").read_text()), [])

    def test_error_mid_capture_still_resets_and_exports_finalempty(self):
        bound = fixture_bound()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "groups.tcl").write_text(b.group_script(b.groups(bound)))
            text = self.run_tcl('set fail_exclude 1\nset failed [catch {apply_reviewed_waivers CoverageTable.1} msg]\n'
                'if {!$failed || $msg ne "Injected capture failure" || $resets != 1 || [array size excluded]} '
                '{error "Not fail closed/reset"}', output, bound)
            self.assertNotIn("LZC_BATCH_CAPTURE_DONE", text)
            self.assertEqual(b.parse_records((output / "final-empty.el").read_text()), [])

    def test_selection_nonprogress_and_leading_zero_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_tcl('lzc_batch_select {01 10}\n'
                'if {$vector_selected ne {01 10}} {error "Names coerced"}\n'
                'set stuck 1\nset failed [catch {lzc_batch_select {01}} msg]\n'
                'if {!$failed || $msg ne "Native deselection did not progress"} {error "Loop did not fail"}',
                Path(tmp), fixture_bound())

    def test_wrong_native_table_still_attempts_reset_and_final_export(self):
        bound = fixture_bound()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "groups.tcl").write_text(b.group_script(b.groups(bound)))
            text = self.run_tcl('set wrong_names 1\nset failed [catch {apply_reviewed_waivers CoverageTable.1} msg]\n'
                'if {!$failed || $resets != 1 || [array size excluded]} {error "Missing cleanup"}', output, bound)
            self.assertNotIn("LZC_BATCH_CAPTURE_DONE", text)
            self.assertEqual(b.parse_records((output / "final-empty.el").read_text()), [])

    def test_tcl_data_quoting_is_not_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = 'x[error injected]$unknown"\\\n; error injected'
            self.run_tcl('set data %s\nif {$data ne %s} {error "Roundtrip differs"}' %
                         (b.tcl_word(value), b.tcl_word(value)), Path(tmp), fixture_bound())

    def test_no_tcl85_only_constructs_or_vector_switch(self):
        text = b.TCL.read_text()
        self.assertNotRegex(text, r"\b(?:dict|lassign|try|finally)\b|\{\*\}")
        self.assertNotIn("-vector", text)


if __name__ == "__main__":
    unittest.main()
