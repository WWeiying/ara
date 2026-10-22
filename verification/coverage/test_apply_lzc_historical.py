"""Focused offline admission and Tcl lifecycle tests; no EDA."""
import copy
import csv
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import apply_lzc_historical as a
from test_capture_lzc_batch import fixture_bound, native_text, TCL_MOCK


class BindingTests(unittest.TestCase):
    def test_relative_pin_keeps_digest_and_rejects_traversal(self):
        digest = "a"*64
        self.assertEqual(a.absolute_pins({"verification/out/list.txt":digest}),
                         {str(a.ROOT/"verification/out/list.txt"):digest})
        with self.assertRaises(ValueError):
            a.absolute_pins({"../list.txt":digest})

    def test_raw_zero_only_and_checksum(self):
        row = dict(point=dict(scope="lzc",metric_checksum="20",raw_index=1))
        bitmap = dict(metrics=dict(cond=dict(lzc=dict(checksum="20",width=3,bits="0"))))
        a.assert_zero(bitmap,[row])
        for field,value in (("bits","2"),("checksum","21"),("width",1)):
            bad = copy.deepcopy(bitmap)
            bad["metrics"]["cond"]["lzc"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                a.assert_zero(bad,[row])

    def test_exact_ordered_completed_population(self):
        before = dict(tests=["/test%d.vdb"%i for i in range(688)])
        state = dict(status="COMPLETE",coverage_status="COMPLETE",aggregate_passed=688)
        inputs = ["/design.vdb",*before["tests"],"/new.vdb"]
        with patch.object(Path,"resolve",lambda self,**kw:self):
            self.assertEqual(a.membership(inputs,before,inputs[-1],inputs[0],state),inputs)
            for changed in (inputs[:-1],inputs[:1]+list(reversed(inputs[1:])),inputs[:-1]+[inputs[1]]):
                with self.assertRaises(ValueError):
                    a.membership(changed,before,inputs[-1],inputs[0],state)
            with self.assertRaises(ValueError):
                a.membership(inputs,before,inputs[-1],inputs[0],dict(state,status="FAIL"))

    def test_sha_required_before_any_launch(self):
        for sha in (None,"", "a"*63,"G"*64):
            with self.subTest(sha=sha), self.assertRaisesRegex(ValueError,"SHA256"):
                a.run(Path("/nonexistent"),sha)

    def test_exact_records_no_selector_or_whole_condition(self):
        bound = fixture_bound()
        text = native_text(bound)
        a.capture.bind_records(a.capture.parse_records(text),bound["candidates"])
        for changed in (text+text,text.replace('(2 "01")','',1)):
            with self.assertRaises(ValueError):
                a.capture.bind_records(a.capture.parse_records(changed),bound["candidates"])
        self.assertNotIn("proc apply_reviewed_waivers",a.capture_helpers())


@unittest.skipUnless(shutil.which("tclsh"),"tclsh required")
class HookTests(unittest.TestCase):
    def exercise(self, injection="", failure=False):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            bound = fixture_bound()
            (output/"groups.tcl").write_text(a.capture.group_script(a.capture.groups(bound)))
            (output/"capture-helpers.tcl").write_text(a.capture_helpers())
            (output/"points.el").write_text(native_text(bound))
            script = 'set env(DVE_COVERAGE_OUTPUT) %s\nsource %s\n'%(
                a.capture.tcl_word(output),a.capture.tcl_word(a.TCL))
            script += TCL_MOCK
            script += '\nset native_text %s\n'%a.capture.tcl_word(native_text(bound))
            script += r'''
proc gui_list_expand {args} {}
proc gui_list_get_property {args} {if {[arg $args -column] == 5} {return Condition}; return ""}
proc export_rows {stream id name depth columns} {global row_count; incr row_count; csv_row $stream {dut 0 80}}
'''
            script += injection+'\nset failed [catch {apply_reviewed_waivers CoverageTable.1} msg]\n'
            script += 'if {$failed != %d || $resets != 1 || [array size excluded]} {puts stderr "Unexpected lifecycle: $failed $msg $resets"; exit 1}\n'%int(failure)
            result = subprocess.run(["tclsh"],input=script,text=True,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(a.capture.parse_records((output/"final-empty.el").read_text()),[])
            if failure:
                self.assertNotIn("LZC_FORMAL_WAIVER_DONE",result.stdout)
            else:
                self.assertIn("LZC_FORMAL_WAIVER_DONE 180",result.stdout)
                records = a.capture.parse_records((output/"exclusions.el").read_text())
                a.capture.bind_records(records,bound["candidates"])
                with (output/"neighbor-audit.csv").open(newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows),360)
                self.assertTrue(all(r["RetainedExcluded"] == "0" for r in rows))
                dual = [r for r in rows if r["Targets"] == "01 10"]
                self.assertEqual(len(dual),180)
                self.assertTrue(all(r["TargetExcluded"] == ("2" if r["Stage"] == "applied" else "0") for r in dual))
                self.assertEqual((output/"initial-empty.el").read_text(),"")

    def test_success_boolean_dual_targets_neighbors_reset(self):
        self.exercise()

    def test_import_missing_one_target_fails_and_resets(self):
        self.exercise(r'''
rename gui_exclusion_file original_file
proc gui_exclusion_file {args} {
    global excluded lzc_batch_groups
    original_file {*}$args
    if {[lsearch -exact $args -load] >= 0} {
        set g [lindex $lzc_batch_groups 0]
        unset excluded([lindex $g 0],[lindex $g 1],10)
    }
}
'''.replace('original_file {*}$args','eval original_file $args'),True)

    def test_retained_neighbor_excluded_fails_and_resets(self):
        self.exercise(r'''
rename gui_exclusion_file original_file
proc gui_exclusion_file {args} {
    global excluded lzc_batch_groups
    eval original_file $args
    if {[lsearch -exact $args -load] >= 0} {
        set g [lindex $lzc_batch_groups 0]
        set excluded([lindex $g 0],[lindex $g 1],00) 1
    }
}
''',True)

    def test_review_required_fails_and_resets(self):
        self.exercise('proc gui_cov_excl_review {args} {return 0}',True)

    def test_tcl84_and_exact_native_import_only(self):
        text = a.TCL.read_text()
        self.assertNotRegex(text,r"\b(?:dict|lassign|try|finally)\b|\{\*\}")
        self.assertNotIn("gui_exclude_items",text)
        self.assertNotIn("-vector",text)


if __name__ == "__main__":
    unittest.main()
