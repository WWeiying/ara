import subprocess
import unittest

import c910_srt_datapath_native_recovery as recovery


class RecoveryTests(unittest.TestCase):
    def test_actual_origin_exact_binding(self):
        c = recovery.base.life.read_bound(recovery.ORIGIN / 'config.json', recovery.ORIGIN_SEAL)
        native = recovery.parent.parse_el((recovery.ORIGIN / 'first.el').read_text(), c)
        expected = recovery.parent.parse_el((recovery.ORIGIN / 'candidate.el').read_text(), c)
        self.assertEqual(native, expected)
        self.assertEqual(len(native), 1264)
        self.assertEqual(sum(len(i['protected']) for i in c['instances']), 416)

    def test_actual_script_uses_absolute_source_without_info_script(self):
        text = recovery.base.TCL.read_text()
        self.assertNotIn('[info script]', text)
        script = 'set ::c910_recovery_test_only 1\n' + text + '\nputs [info procs c910_session]\n'
        result = subprocess.run(['tclsh'], input=script, text=True,
                                capture_output=True, timeout=10, cwd='/tmp')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout.strip(), 'c910_session')

    def test_real_recovery_session_no_click_and_stage_order(self):
        script = 'set ::c910_recovery_test_only 1\n' + recovery.base.TCL.read_text() + r'''
rename c910_session real_session
proc source {args} {
    set ::fma_instances [list [list scope targets protected 0]]
    set ::fma_design design
    set ::fma_vdb vdb
    set ::fma_test test
}
set ::env(DVE_COVERAGE_OUTPUT) /tmp
set ::calls {}
proc c910_primitives {} {}
proc gui_open_cov {args} {}
proc gui_list_expand {args} {}
proc fma_save {name} {lappend ::calls $name}
proc c910_bind {stage instance} {lappend ::calls $stage}
proc gui_exclusion_file {args} {lappend ::calls load_origin}
proc gui_exclusion {args} {lappend ::calls [lindex $args end]}
proc gui_cov_excl_review {args} {return 1}
proc fma_need {ok why} {if {!$ok} {error $why}}
proc fma_check {name} {lappend ::calls check_$name}
proc gui_process_events {args} {}
proc c910_load {name} {lappend ::calls load_$name}
proc gui_list_select {args} {error NO_CLICKS_ALLOWED}
real_session
puts $::calls
'''
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.stderr, '')
        self.assertIn('initial-empty.el before load_origin -recalculate selected first.el', result.stdout)
        self.assertIn('-reset -recalculate reset reset-empty.el load_first.el reloaded second.el',
                      result.stdout)
        self.assertIn('-reset -recalculate final final-empty.el', result.stdout)


if __name__ == '__main__':
    unittest.main()
