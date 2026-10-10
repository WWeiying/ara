import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import observe_cvxif_point_identity789 as owner


class ReadOnlyEntry(unittest.TestCase):
    def execute(self, body):
        return subprocess.run(['tclsh'], input=body, text=True, capture_output=True, timeout=10)

    def test_standalone_entry_exact_two_queries(self):
        # Execute the real entry through source boundaries; GUI command allowlist.
        script = '''
set ::point_test_only 1
set ::env(DVE_COVERAGE_OUTPUT) /not-written
set calls {}
rename source original_source
proc source {path} {
    if {[file tail $path] eq "selection.tcl"} {
        set ::point_library library; set ::point_selector selector
        set ::cv_design design; set ::cv_vdb vdb; set ::cv_test test
        set ::point_scope ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind
    }
}
proc gui_open_cov {args} {lappend ::calls open}
proc cv_snapshot {stage metric index scope} {
    if {$stage ne "observed" || $index != 0 || $scope ne $::point_scope} {error foreign}
    lappend ::calls $metric
}
'''+owner.HOOK.read_text()+'''
if {[catch {point789_session} message]} {puts stderr $message; exit 1}
if {$calls ne {open Line Branch}} {error "Wrong calls $calls"}
puts HOST_ENTRY_PASS
'''
        result = self.execute(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('HOST_ENTRY_PASS', result.stdout)

    def test_no_mutation_commands_in_entry(self):
        text = owner.HOOK.read_text()
        for command in ('gui_exclude_items', 'gui_exclusion_file', 'gui_exclusion ', 'cv_apply', 'cv_save', 'cv_reset'):
            self.assertNotIn(command, text)

    def test_actual_v2_selector_never_uses_meta_query(self):
        text = (owner.HERE/'capture_cvxif_passive_two_scope770_v2.tcl').read_text()
        text = text[text.index('proc cv_select_detail'):text.rindex('if {!$cv_external_test}')]
        prefix = '''
set selected {}
proc cv_need {ok why} {if {!$ok} {error $why}}
proc gui_list_get_selected {args} {
    if {[lsearch -exact $args -meta] >= 0} {error unsupported-meta}
    if {[lsearch -exact $args -count] >= 0} {return [llength $::selected]}
    if {[lsearch -exact $args -first] >= 0} {return [lindex $::selected 0]}
    return $::selected
}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::selected {}; return}
    set ::selected [lindex $args end]
}
'''
        result = self.execute(prefix+text+'\ncv_select_detail exact exact\nputs SELECT_PASS\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SELECT_PASS', result.stdout)
        result = self.execute(prefix+text+'''
rename gui_list_get_selected actual_get
proc gui_list_get_selected {args} {
    if {[lsearch -exact $args -first] >= 0} {return foreign}
    return [eval actual_get $args]
}
if {![catch {cv_select_detail exact exact}]} {exit 1}
puts FOREIGN_REJECTED
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FOREIGN_REJECTED', result.stdout)

    def test_foreign_service_rejected_before_launch(self):
        with patch.object(owner, 'check', return_value={}), patch.object(Path, 'read_text', return_value='foreign.service'):
            with self.assertRaises(ValueError): owner.run(Path('/not-written'), 'seal', True)

    def test_unsafe_tcl_literal_rejected(self):
        for value in ('bad{scope', 'bad\npath', 'bad\\path'):
            with self.assertRaises(ValueError): owner.quote(value)


if __name__ == '__main__': unittest.main()
