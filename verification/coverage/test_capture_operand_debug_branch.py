import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_operand_debug_branch as b
from test_capture_operand_debug import fixture, native


def original_plan():
    config = fixture()
    scope = "top.requester"
    rows = config["plan"]["scopes"][scope]["branch"]
    zero = copy.deepcopy(rows[0])
    zero["coordinate"] = "3,0"
    zero["point"]["vector"] = "0"
    protected = copy.deepcopy(rows[0])
    protected.update(coordinate="8,21", target=False)
    protected["point"].update(native_id="8", vector="21")
    rows.extend([zero, protected])
    return config["plan"]


class BranchOnlyTests(unittest.TestCase):
    def test_pilot_exact_two_and_functional_default_protected(self):
        plan = b.branch_plan(original_plan(), "pilot")
        self.assertEqual(set(plan["scopes"]["top.requester"]), {"branch"})
        rows = plan["scopes"]["top.requester"]["branch"]
        self.assertEqual({r["coordinate"] for r in rows if r["target"]}, {"3,0", "3,4"})
        self.assertFalse(next(r["target"] for r in rows if r["coordinate"] == "8,21"))

    def test_cannot_target_functional_default(self):
        plan = original_plan()
        plan["scopes"]["top.requester"]["branch"][-1]["target"] = True
        with self.assertRaises(ValueError):
            b.branch_plan(plan, "full")

    def test_unreviewed_pilot_rejected(self):
        plan = original_plan()
        plan["scopes"]["top.requester"]["branch"][0]["target"] = False
        with self.assertRaises(ValueError):
            b.branch_plan(plan, "pilot")

    def test_line_and_recursive_commands_absent(self):
        text = b.TCL.read_text()
        self.assertNotIn("-column Line", text)
        self.assertNotIn("-recursive", text)
        self.assertIn("MISSING_DEFAULT", text)
        self.assertIn("scope=$scope parent=$parentpath meta=$meta path=$path children=$children", text)

    def test_first_native_extra_line_rejected(self):
        config = dict(plan=b.branch_plan(original_plan(), "pilot"))
        with self.assertRaises(ValueError):
            b.debug.bind_native(native(), config)

    def test_tcl_real_metadata_forms_and_boolean_audit(self):
        prelude = b.TCL.read_text().split("set failed [catch {dbg_session} message]", 1)[0]
        with tempfile.TemporaryDirectory() as d:
            script = prelude + '''
set env(DVE_COVERAGE_OUTPUT) {%s}
set dbg_scopes {scope}
set dbg_keys(scope|branch) {3,0 3,4 8,21}
set dbg_targets(scope|branch) {3,0 3,4}
array set metas {p3 Item3 a Branch3.0 z MISSING_ELSE3.4 p8 Item8 d MISSING_DEFAULT8.21}
array set paths {p3 Item3 a Item3.Branch3.0 z Item3.MISSING_ELSE3.4 p8 Item8 d Item8.MISSING_DEFAULT8.21}
array set first {p3 a p8 d}
array set next {p3 p8 a z}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Branch}
proc gui_list_expand {args} {}
proc gui_list_get {args} {
    global metas paths first next
    set option [lindex $args 2]
    set item [lindex $args 3]
    switch -- $option {
        -firstChild {if {$item eq ""} {return p3}; if {[info exists first($item)]} {return $first($item)}; return 0}
        -nextSibling {if {[info exists next($item)]} {return $next($item)}; return 0}
        -meta {return $metas($item)}
        -path {return $paths($item)}
        -childCount {return 0}
        default {error "Unknown mock API"}
    }
}
set selected {}
proc gui_list_get_selected {args} {global selected; return $selected}
proc gui_list_select {args} {
    global selected
    if {[lsearch -exact $args -unselect] >= 0} {set selected {}; return}
    set selected [lindex $args end]
}
set active 0
proc gui_exclusion {args} {
    global selected active
    if {[llength $selected] != 1} {error "Not singleton"}
    return [expr {$active && [lindex $selected 0] ne "MISSING_DEFAULT8.21"}]
}
dbg_audit before 0
set active 1
dbg_audit selected 1
set active 0
dbg_audit final 0
if {![catch {dbg_metadata scope line}]} {error "Line not held"}
puts PASS
''' % d
            result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertIn("PASS", result.stdout)
            selected = (Path(d) / "states_selected.tsv").read_text()
            self.assertIn("scope\tbranch\t8,21\tMISSING_DEFAULT8.21\tItem8.MISSING_DEFAULT8.21\t0", selected)

    def test_bad_pilot_receipt_never_enables_full(self):
        with tempfile.TemporaryDirectory(dir=b.debug.OUT) as d:
            path = Path(d)
            (path / "capture-result.json").write_text('{"status":"FAILED"}')
            with self.assertRaises(ValueError):
                b.pin_result(path, "0" * 64, b.sha(path / "capture-result.json"))


if __name__ == "__main__":
    unittest.main()
