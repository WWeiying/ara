from pathlib import Path
import subprocess
import tempfile
import unittest

import fsm741_native_probe as p


class NativeProbe(unittest.TestCase):
    def test_real_tcl_proc_context_readonly(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / 'DVEfiles').mkdir()
            (out / 'live-ready').touch()
            (out / 'DVEfiles/dve_gui.log').write_text("The design '/frozen/design.vdb' was loaded successfully.\n")
            script = '''
set fp_test_only 1
source {%s}
set env(FSM_PROBE_OUTPUT) {%s}
set env(FSM_PROBE_DESIGN) /frozen/design.vdb
set env(FSM_PROBE_SAMPLE) /frozen/sample.vdb
set env(FSM_PROBE_SELECTED) /frozen/sample/test
proc help {args} {return HELP_ONLY}
proc gui_open_cov {args} {}
proc gui_get_window_ids {} {return CoverageTable.1}
proc gui_list_expand {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return FSM}
proc gui_covdetail_select {args} {
    if {[lsearch -exact $args -fsmMode] >= 0} {
        set ::mode [lindex $args [expr {[lsearch -exact $args -fsmMode]+1}]]
    }
}
proc gui_list_select {args} {}
proc gui_dump_common_list {args} {return {Name Coverage}}
proc gui_list_get {args} {return 0}
proc gui_list_get_selected {args} {
    if {[lindex $args 3] eq "fsmnames"} {
        if {[lsearch -exact $args -first] >= 0} {return {{ state_q }}}
        return state_q
    }
    if {[info exists ::mode] && $::mode eq "Transition"} {return {IDLE->READ}}
    return IDLE
}
proc gui_exclusion {args} {error EXCLUSION_FORBIDDEN}
proc gui_exclude_items {args} {error EXCLUSION_FORBIDDEN}
proc gui_exclusion_file {args} {error EXCLUSION_FORBIDDEN}
if {[catch {fp_session} err]} {puts stderr "$err\n$::errorInfo";exit 1}
''' % (p.HOOK, out)
            result = subprocess.run(['/usr/bin/tclsh'], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('FSM741_READONLY_PROBE_DONE', result.stdout)
            text = (out / 'native-token-api.tsv').read_text()
            self.assertIn('IDLE->READ', text)
            self.assertIn('gui_exclude_items', text)
            self.assertFalse(list(out.glob('*.el')))


if __name__ == '__main__':
    unittest.main()
