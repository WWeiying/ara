import copy
import csv
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_operand_debug as c


def fixture():
    line = dict(native_id="22", vector="", file_id="552", line="1102", expression="if (rst_ni)",
                statements=[dict(file_id="552", line_num="1102")])
    branch = dict(native_id="3", vector="4", file_id="552", line="1102", expression="rst_ni",
                  attributes=dict(chksum="88"), native_vector=dict(vector="100000"),
                  expressions=[dict(file_id="552", id="1102", exprstr="rst_ni",
                                    true_clause_line="1103", false_clause_line="1111")])
    rows = {m: [dict(point=p, coordinate=c.coordinate(p, m), target=True,
                    module_checksum="11", metric_checksum="22")] for m, p in (("line", line), ("branch", branch))}
    return dict(plan=dict(scopes={"top.requester": rows}))


def native():
    return ('CHECKSUM: "11 22"\nINSTANCE: top.requester\nANNOTATION: "' + c.ANNOTATION +
            '"\nBlock 22 "123" "if (rst_ni)"\nANNOTATION: "' + c.ANNOTATION +
            '"\nBranch 3 "88" "rst_ni" (4) "rst_ni 1,-,default"\n').encode()


class DebugCaptureTests(unittest.TestCase):
    def test_complete_line(self):
        p = fixture()["plan"]["scopes"]["top.requester"]["line"][0]["point"]
        self.assertTrue(c.complete(p, "line", "552"))
        p["statements"].append(dict(file_id="552", line_num="619"))
        self.assertFalse(c.complete(p, "line", "552"))

    def test_mixed_file_rejected(self):
        p = fixture()["plan"]["scopes"]["top.requester"]["line"][0]["point"]
        p["statements"][0]["file_id"] = "99"
        with self.assertRaises(ValueError):
            c.complete(p, "line", "552")

    def test_empty_object_rejected(self):
        p = fixture()["plan"]["scopes"]["top.requester"]["line"][0]["point"]
        p["statements"] = []
        with self.assertRaises(ValueError):
            c.complete(p, "line", "552")

    def test_clause_endpoint_protected(self):
        p = fixture()["plan"]["scopes"]["top.requester"]["branch"][0]["point"]
        self.assertTrue(c.complete(p, "branch", "552"))
        p["expressions"][0]["false_clause_line"] = "1141"
        self.assertFalse(c.complete(p, "branch", "552"))

    def test_region_crossing_rejected(self):
        p = fixture()["plan"]["scopes"]["top.requester"]["line"][0]["point"]
        p["statements"].append(dict(file_id="552", line_num="650"))
        self.assertFalse(c.complete(p, "line", "552"))

    def test_native_text_signature_not_xml_bitstring(self):
        rows = c.bind_native(native(), fixture())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["native_signature"], "rst_ni 1,-,default")

    def test_native_wrong_binding(self):
        for old, new in ((b'Block 22', b'Block 23'), (b'Branch 3 "88"', b'Branch 3 "89"'),
                         (b'11 22', b'11 23'), (b'"if (rst_ni)"', b'"other"')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                c.bind_native(native().replace(old, new), fixture())

    def test_extra_duplicate_and_whole_instance_rejected(self):
        for raw in (native() + native(), native() + b'Toggle data "logic data"\n',
                    b'CHECKSUM: "11 22"\nINSTANCE: top.requester\n'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                c.bind_native(raw, fixture())

    def test_annotation_mandatory(self):
        for raw in (native().replace(c.ANNOTATION.encode(), b'other'),
                    native().replace(('ANNOTATION: "' + c.ANNOTATION + '"\n').encode(), b'')):
            with self.assertRaises(ValueError):
                c.bind_native(raw, fixture())

    def test_protected_complement_audit(self):
        config = fixture()
        rows = config["plan"]["scopes"]["top.requester"]["line"]
        protected = copy.deepcopy(rows[0])
        protected.update(coordinate="23", target=False)
        rows.append(protected)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.tsv"
            def emit(excluded, omit=False):
                with path.open("w", newline="") as stream:
                    writer = csv.writer(stream, delimiter="\t")
                    writer.writerow(["scope", "metric", "coordinate", "meta", "path", "excluded"])
                    writer.writerow(["top.requester", "line", "22", "Block22", "Block22", "1"])
                    writer.writerow(["top.requester", "branch", "3,4", "Branch3.4", "Item3.Branch3.4", "1"])
                    if not omit:
                        writer.writerow(["top.requester", "line", "23", "Block23", "Block23", excluded])
            emit("0")
            c.audit_states(path, config, "selected")
            for value, omit in (("1", False), ("0", True)):
                emit(value, omit)
                with self.assertRaises(ValueError):
                    c.audit_states(path, config, "selected")

    def test_tcl_singleton_boolean_selection(self):
        script = '''set dbg_library_only 1
source {%s}
set selected {}
proc gui_list_get_selected {args} {global selected; return $selected}
proc gui_list_select {args} {
    global selected
    if {[lsearch -exact $args -unselect] >= 0} {set selected {}; return}
    set selected [lindex $args end]
}
proc gui_exclusion {args} {return 1}
dbg_select branch Branch3.4
dbg_require [expr {[llength $selected] == 1}] bad
dbg_select line Block22
dbg_require [expr {$selected eq "Block22"}] bad
puts PASS
''' % c.TCL
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
