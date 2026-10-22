from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
HELPER = HERE / 'six_policy_singleton_selection_v2.tcl'
FROZEN = HERE / 'capture_operand_debug.tcl'


class SelectionTests(unittest.TestCase):
    def invoke(self, commands):
        prefix = '''
set dbg_library_only 1
source {%s}
source {%s}
set selected "{ }"
set calls {}
proc gui_list_get_selected {args} {global selected; return $selected}
proc gui_list_select {args} {
    global selected calls
    lappend calls $args
    if {[lindex $args end-1] eq "-unselect"} {
        foreach item [lindex $args end] {
            if {[string trim $item] eq ""} {error {gui_list_select: List item(s) given by "" were not found.}}
        }
        set selected {}
    } else {set selected [lindex $args end]}
}
''' % (FROZEN, HELPER)
        return subprocess.run(['tclsh'], input='if {[catch {\n' + prefix + commands +
                              '\n} message]} {puts stderr $message; exit 1}\n',
                              text=True, capture_output=True)

    def test_frozen_helper_reproduces_empty_unselect(self):
        result = self.invoke('dbg_select branch Branch33.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('given by ""', result.stderr)

    def test_successor_skips_only_empty_sentinel(self):
        result = self.invoke('six2_install_selection_adapter\ndbg_select branch Branch33.1\n'
                             'if {[llength $calls] != 1} {error BAD_CALL_COUNT}\nputs PASS')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], 'PASS')
        self.assertIn('SIX2_EMPTY_SELECTION_NORMALIZED', result.stdout)

    def test_valid_prior_selection_is_explicitly_cleared(self):
        result = self.invoke('six2_install_selection_adapter\nset selected {{Branch32.0}}\n'
                             'dbg_select branch MISSING_DEFAULT33.0\n'
                             'if {[llength $calls] != 2} {error BAD_CALL_COUNT}\nputs PASS')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_nonempty_selection_is_not_skipped(self):
        result = self.invoke('six2_install_selection_adapter\nset selected FOREIGN\ndbg_select branch Branch33.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unknown nonempty', result.stderr)

    def test_wrong_singleton_readback_rejected(self):
        result = self.invoke('six2_install_selection_adapter\nrename gui_list_select old_select\n'
                             'proc gui_list_select {args} {global selected; set selected Branch99.0}\n'
                             'dbg_select branch Branch33.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('readback differs', result.stderr)

    def test_mixed_empty_and_valid_does_not_hide_items(self):
        result = self.invoke('six2_install_selection_adapter\nset selected [list Branch32.0 {}]\n'
                             'dbg_select branch Branch33.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unknown nonempty', result.stderr)


if __name__ == '__main__':
    unittest.main()
