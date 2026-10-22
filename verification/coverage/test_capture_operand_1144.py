import copy
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_operand_1144 as capture


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.raw = ('CHECKSUM: "1532764271 1417162425"\nINSTANCE: queue\n'
                    'ANNOTATION: "%s"\nBranch 4 "99" "expr" (0) "expr 1,0"\n' % capture.ANNOTATION).encode()
        self.expected = {"queue|Branch 4 (0)": dict(module_checksum="1532764271", metric_checksum="1417162425",
                                                   spec_checksum="99", expression="expr")}
        self.plan = dict(design_vdb="/design", selected_test_vdb="/test", scopes={"queue": dict(
            targets=[dict(selector="4,0", raw_index=0)], protected=[dict(selector="4,1", raw_index=1)])})

    def test_native_binding_and_full_signature_preserved(self):
        rows = capture.parse_native(self.raw)
        capture.bind_native(rows, self.expected, rows)
        changed = capture.parse_native(self.raw.replace(b"expr 1,0", b"expr 0,1"))
        self.assertNotEqual(rows, changed)
        with self.assertRaises(ValueError):
            capture.bind_native(changed, self.expected, rows)

    def test_native_extra_duplicate_wildcard_or_foreign_directive_reject(self):
        for bad in (self.raw+self.raw, self.raw.replace(b"queue\n", b"queue.*\n"),
                    self.raw.replace(b"Branch 4", b"Block 4"), self.raw+b"UNKNOWN\n",
                    self.raw+b'CHECKSUM: "1532764271 1417162425"\nINSTANCE: queue2\n'):
            with self.assertRaises(ValueError):
                capture.parse_native(bad)
        with self.assertRaises(ValueError):
            capture.bind_native(capture.parse_native(self.raw), {}, {})

    def test_checksum_expression_annotation_reject(self):
        for old, new in ((b"1532764271", b"1"), (b'"99"', b'"98"'),
                         (b'"expr"', b'"other"'), (capture.ANNOTATION.encode(), b"approval")):
            with self.assertRaises(ValueError):
                capture.bind_native(capture.parse_native(self.raw.replace(old, new)), self.expected, {})

    def test_environment_explicitly_pops_dve(self):
        with patch.object(capture.tool, "controlled_environment", return_value={"DVE": "/wrong", "PATH": "/usr/bin:/bin"}):
            env = capture.environment({}, Path("/output"))
        self.assertNotIn("DVE", env)
        self.assertEqual(env["DVE_COVERAGE_OUTPUT"], "/output")

    def test_selection_requires_full_unique101_and_tcl_safe_scope(self):
        with self.assertRaises(ValueError):
            capture.selection(self.plan)
        with self.assertRaises(ValueError):
            capture.literal("bad} ; exec malicious")
        plan = copy.deepcopy(self.plan)
        plan["scopes"]["queue"]["protected"] = [dict(selector="4,%d" % n, raw_index=n) for n in range(1, 101)]
        text = capture.selection(plan)
        result = subprocess.run(["tclsh"], input=text+'puts [llength $op1144_keys(queue)]\nputs $op1144_targets(queue)\n',
                                text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), ["101", "4,0"])

    def make_states(self, path, excluded="0", missing=False, duplicate=False, meta="Branch4.1"):
        rows = [dict(scope="queue", coordinate="4,0", meta="Branch4.0", path="Item4.Branch4.0", excluded="1"),
                dict(scope="queue", coordinate="4,1", meta=meta, path="Item4."+meta, excluded=excluded)]
        if missing:
            rows.pop()
        if duplicate:
            rows.append(rows[0])
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["scope", "coordinate", "meta", "path", "excluded"], delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    def test_states_protected_missing_duplicate_nonboolean_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "states.tsv"
            self.make_states(path)
            capture.states(path, self.plan, "selected")
            for kwargs in (dict(excluded="1"), dict(excluded="2"), dict(missing=True),
                           dict(duplicate=True), dict(meta="Branch4.2")):
                self.make_states(path, **kwargs)
                with self.assertRaises(ValueError):
                    capture.states(path, self.plan, "selected")

    def test_states_roundtrip_metadata_cannot_float(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "states.tsv"
            self.make_states(path)
            original = capture.states(path, self.plan, "selected")
            self.make_states(path, meta="MISSING_ELSE4.1")
            with self.assertRaises(ValueError):
                capture.states(path, self.plan, "reloaded", original)

    def test_tcl_singleton_boolean_api_and_protected_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            script = '''set op1144_library_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set op1144_scopes {queue}
array set op1144_keys {queue {4,0 4,1}}
array set op1144_targets {queue {4,0}}
set selection {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Branch}
proc gui_list_expand {args} {}
proc gui_list_get_selected {args} {return $::selection}
proc gui_list_select {args} {
    if {[lindex $args 4] eq "-unselect"} {set ::selection {}} else {set ::selection [lindex $args 5]}
}
proc gui_list_get {args} {
    set op [lindex $args 2]
    set item [lindex $args 3]
    switch -- $op {
        -firstChild {if {$item eq ""} {return P}; if {$item eq "P"} {return L0}; return 0}
        -nextSibling {if {$item eq "L0"} {return L1}; return 0}
        -path {if {$item eq "P"} {return Item4}; if {$item eq "L0"} {return Item4.Branch4.0}; return Item4.Branch4.1}
        -meta {if {$item eq "L0"} {return Branch4.0}; return Branch4.1}
        -childCount {return 0}
        default {error "Unknown API"}
    }
}
proc gui_exclusion {args} {
    if {[llength $::selection] != 1} {error "No multi-selection query permitted"}
    if {$::bad} {return 1}
    return [expr {[lindex $::selection 0] eq "Branch4.0"}]
}
set bad 0
if {[catch {op1144_audit selected 1} message]} {puts stderr $message; exit 1}
set bad 1
if {![catch {op1144_audit selected 1}]} {puts stderr "Protection failed open"; exit 1}
puts MOCK_SINGLETON_PASS
''' % (capture.TCL, directory)
            result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("MOCK_SINGLETON_PASS", result.stdout)

    def test_config_requires_external_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                capture.config_read(Path(directory), None)


if __name__ == "__main__":
    unittest.main()
