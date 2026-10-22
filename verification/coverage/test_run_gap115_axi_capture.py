import json
import subprocess
import unittest
import run_gap115_axi_capture as m


class Focused(unittest.TestCase):
    def test_exact_command_only_paths_and_debug_added(self):
        old = json.loads((m.OLD/'manifest.json').read_bytes())['command']
        new = m.command(old)
        unchanged = [x for x in old if not x.startswith(('+COMMIT_TRACE=', '+VECTOR_TRACE='))]
        unchanged[unchanged.index('-cm_dir')+1] = str(m.OUT/'code.vdb')
        self.assertEqual([x for x in new[:-3] if not x.startswith(('+COMMIT_TRACE=', '+VECTOR_TRACE='))], unchanged)
        self.assertEqual(new[-3:], ['-ucli', '-do', str(m.TCL)])
        self.assertEqual([x for x in new if x.startswith('+PRELOAD=')], [x for x in old if x.startswith('+PRELOAD=')])

    def test_duplicate_or_missing_path_rejected(self):
        old = json.loads((m.OLD/'manifest.json').read_bytes())['command']
        for bad in (old+['+COMMIT_TRACE=foreign'], [x for x in old if not x.startswith('+VECTOR_TRACE=')]):
            with self.assertRaises(ValueError): m.command(bad)

    def tcl(self, fail):
        script = '''
set seen {}
proc dump {args} {
    global seen
    if {[lindex $args 0] eq "-file"} {return VPD0}
    lappend seen [lindex $args 1]
    return 1
}
proc show {args} {if {FAIL && [string match *axi_resp_i [lindex $args end]]} {error "No object"}}
proc run {} {global seen; puts "RUN_OBJECTS=$seen"}
source {SCRIPT}
'''.replace('FAIL', str(int(fail))).replace('SCRIPT', str(m.TCL))
        return subprocess.run(['tclsh'], input=script, text=True, capture_output=True)

    def test_four_actual_tcl_objects_and_no_hierarchy(self):
        r = self.tcl(False); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count('GAP115_AXI_OBJECT '), 4)
        self.assertIn('GAP115_AXI_FOUR_OBJECTS_READY', r.stdout)
        self.assertIn('RUN_OBJECTS=', r.stdout)
        self.assertNotIn('force ', m.TCL.read_text())

    def test_missing_object_fails_before_run(self):
        r = self.tcl(True); self.assertNotEqual(r.returncode, 0)
        self.assertIn('GAP115_AXI_CAPTURE_ERROR', r.stderr); self.assertNotIn('RUN_OBJECTS=', r.stdout)


if __name__ == '__main__': unittest.main()
