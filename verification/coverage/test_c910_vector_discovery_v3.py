"""Host fixtures test gates, not native API capability."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import c910_vector_discovery_v3 as m
from test_c910_vector_discovery_v2 import FIXTURE

OVERRIDES = r'''
set selected [list {bound_sel[6:0]} {old item with spaces}]
set phase main
proc entries {} {return [list {initial_divisor_in[55:0]}]}
proc gui_list_get_selected {args} {
    global selected mode
    if {[lsearch -exact $args -count] >= 0} {
        if {$mode eq "badcount" && [llength $selected] == 0} {return 1}
        if {$mode eq "selectcount" && [llength $selected] == 1} {return 2}
        return [llength $selected]
    }
    set groups {}
    foreach token $selected {lappend groups [list [list $token]]}
    if {$mode eq "malformed"} {return [list [list [list one two]]]}
    if {$mode eq "emptygroup"} {return [list {}]}
    if {$mode eq "wrongreadback" && [llength $selected] == 1} {
        return [list [list [list foreign]]]
    }
    return $groups
}
proc gui_list_select {args} {
    global selected mode phase
    set token [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -unselect] >= 0} {
        if {$mode eq "unselecterror"} {error actual_unselect_failure}
        set i [lsearch -exact $selected $token]
        if {$i < 0} {error exact_token_not_found}
        set selected [lreplace $selected $i $i]
    } else {
        lappend selected $token
        set phase detail
    }
    return {}
}
proc gui_list_get_property {args} {
    global phase mode
    set labels [list Variable { } {  } {   } Type Coverage Display]
    if {$phase eq "detail" && $mode ne "mainonly"} {
        set labels [list Variable { } {  } {   } 0->1 1->0]
    }
    if {$mode eq "changedheader" && $phase eq "detail"} {lset labels 1 {}}
    return [lindex $labels [lindex $args end]]
}
rename gui_list_get original_get
proc gui_list_get {args} {
    global mode
    if {[lsearch -exact $args -path] >= 0} {
        if {$mode eq "badpath"} {return {one two}}
        return [list {native detail token with spaces}]
    }
    return [original_get {*}$args]
}
proc gui_cov_tgl_double_click {args} {
    global clicks mode
    incr clicks
    if {[lindex $args end] ne "native detail token with spaces"} {error wrong_item}
    if {$mode eq "clickerror"} {error actual_click_failure}
    return {}
}
set rc [catch {vd_probe} message]
puts [list outcome $rc $message clicks $clicks]
if {!$rc} {
    set f [open [file join $env(DVE_COVERAGE_OUTPUT) discovery-done.txt] w]
    puts $f C910_SINGLE_SCOPE_DISCOVERY_DONE_NOT_QUALIFICATION
    close $f
} else {
    set f [open [file join $env(DVE_COVERAGE_OUTPUT) discovery-error.txt] w]
    puts $f $message
    close $f
}
'''


class Discovery(unittest.TestCase):
    def fixture(self, out, mode):
        setup = (FIXTURE % (m.TCL, out, mode)).split('vd_capture initial')[0]
        r = subprocess.run(['tclsh'], input=setup + OVERRIDES, text=True,
                           capture_output=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, '')
        return r.stdout

    def reject(self, mode, reason, clicks=0):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            output = self.fixture(out, mode)
            self.assertIn(reason, output)
            self.assertIn('clicks ' + str(clicks), output)
            self.assertTrue((out / 'selected.frames').exists())
            self.assertFalse((out / 'discovery-done.txt').exists())
            with self.assertRaises(ValueError):
                m.capture_gate(out, dict(scope='scope0', test='sample0'))

    def test_grouped_multiple_selection_and_spaces_exact_success(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            self.assertIn('outcome 0 {} clicks 1', self.fixture(out, 'ok'))
            self.assertEqual(m.capture_gate(out, dict(scope='scope0', test='sample0')),
                             dict(initial=1, selected=1, detail_clicked=1))

    def test_unselect_rc1_stops_before_click(self):
        self.reject('unselecterror', 'STOP unselect failed')

    def test_count_not_zero_stops(self):
        self.reject('badcount', 'STOP selection not cleared')

    def test_count_not_one_stops(self):
        self.reject('selectcount', 'STOP exact singleton readback differs')

    def test_wrong_singleton_stops(self):
        self.reject('wrongreadback', 'STOP exact singleton readback differs')

    def test_malformed_group_stops(self):
        self.reject('malformed', 'STOP malformed selected token')

    def test_empty_group_stops(self):
        self.reject('emptygroup', 'STOP empty selected group')

    def test_tokens_preserve_spaces_and_literal_brackets(self):
        script = 'set vd_host_test_only 1\nsource {%s}\n' % m.TCL
        script += r'''
set token {  actual [6:0] token  }
set value [list [list [list $token]]]
if {[vd_tokens $value] ne [list $token]} {error token_changed}
puts EXACT
'''
        r = subprocess.run(['tclsh'], input=script, capture_output=True, text=True, timeout=10)
        self.assertEqual(r.stderr, '')
        self.assertEqual(r.stdout.strip(), 'EXACT')

    def test_main_schema_stops_without_api_fallback(self):
        self.reject('mainonly', 'STOP selection did not expose detail schema')

    def test_changed_blank_header_stops_and_retains_tree(self):
        self.reject('changedheader', 'Unknown full column schema')

    def test_nonunique_path_tokens_stop(self):
        self.reject('badpath', 'STOP no unique exact target detail token')

    def test_click_error_retained_no_second_api(self):
        self.reject('clickerror', 'STOP double_click failed', clicks=1)

    def test_no_EL_no_regex_single_scope_and_bounded_launcher(self):
        text = m.TCL.read_text()
        for name in ('regexp', 'gui_exclusion', 'qc_reset', 'qc_save', 'mq_load'):
            self.assertNotIn(name, text)
        self.assertEqual(text.count('gui_open_cov '), 1)
        self.assertEqual(text.count('gui_cov_tgl_double_click -id'), 1)
        c = dict(launch_contract=dict(unit='one', pythonpath='/host', host_tools=[dict(path=p)
                 for p in ('/usr/bin/systemd-run', '/usr/bin/systemctl', '/usr/bin/python3.9')]))
        cmd = m.service_command(c, Path('/out'), 'a' * 64)
        self.assertIn('--property=RuntimeMaxSec=290', cmd)
        self.assertIn('--property=TimeoutStopSec=10', cmd)
        self.assertNotIn('--collect', cmd)
        self.assertIn(str(m.SCRIPT), cmd)

    def test_precheck_failure_terminal_and_no_EDA(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            with patch.object(m, 'check', side_effect=ValueError('precheck')), \
                 patch.object(m.subprocess, 'Popen') as native:
                with self.assertRaises(ValueError):
                    m.worker(out, 'a' * 64, 'a' * 64)
                native.assert_not_called()
            self.assertTrue((out / 'terminal.json').exists())
            self.assertTrue((out / 'worker-error.json').exists())


if __name__ == '__main__':
    unittest.main()
