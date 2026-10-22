import pathlib
import subprocess
import unittest

HOOK = pathlib.Path(__file__).with_name('fsm741_native_singleton.tcl')


class ContextTest(unittest.TestCase):
    def test_real_proc_requires_explicit_context(self):
        script = '''
set fs_test_only 1
set tab 0
set region 0
set matrix 0
proc gui_open_source {args} {
    global matrix
    if {[lindex $args [expr {[lsearch $args -matrix]+1}]] ne "Fsm"} {error matrix}
    set matrix 1
}
proc gui_covdetail_select {args} {
    global tab region matrix
    if {[lsearch $args -name] >= 0} {set tab 1}
    if {[lsearch $args -region] >= 0} {set region 1}
    if {[lsearch $args -fsmMode] >= 0 && (!$matrix || !$tab || !$region)} {error DVTC020}
}
proc gui_list_select {args} {}
proc gui_list_get_selected {args} {return state_q}
source {%s}
if {![catch {gui_covdetail_select -id CovDetail.1 -fsmMode State}]} {error "missing context accepted"}
fs_context exactscope
puts CONTEXT_PASS
''' % HOOK
        result = subprocess.run(['tclsh'], input='if {[catch {\n' + script + '\n} msg]} {puts stderr $msg; exit 1}\n',
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CONTEXT_PASS', result.stdout)

    def test_cleanup_is_independent_and_no_idle_exclusion(self):
        text = HOOK.read_text()
        self.assertIn('fs_select KILL_MISS\n    gui_exclude_items', text)
        self.assertIn('catch {gui_exclusion -reset}', text)
        self.assertIn('catch {fs_save final-empty.el 1}', text)
        self.assertIn('fs_audit reloaded 1', text)


if __name__ == '__main__':
    unittest.main()
