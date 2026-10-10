import copy
import subprocess
import unittest
import run_external_tbpin_reset as m


class SharedReset(unittest.TestCase):
    def config(self):
        return dict(route='fixture_EX2', stage='ara_tb.dut.ctrl.div_cur_state', code=6,
                    valids=['ara_tb.dut.ctrl.busy', 'ara_tb.dut.ctrl.half'])

    def mock(self, mode='normal', call=None):
        t = self.config()
        script = r'''
set mode MODE
set armed 0
set edge 0
set reset 1
set deposits {}
set armed_command {}
proc show {args} {return reg}
proc dump {args} {if {[lindex $args 0] eq "-file"} {return fid}; return 1}
proc stop {args} {
    global armed armed_command
    if {[lrange $args 0 2] ne {-once -negedge ara_tb.clk}} {error "Wrong arm edge"}
    set armed 1
    set armed_command [lindex $args [expr {[lsearch -exact $args -command]+1}]]
}
proc get {path args} {
    global mode reset
    if {$args ne {-radix decimal}} {error "Wrong radix"}
    if {$path eq "ara_tb.rst_n"} {return $reset}
    if {[string match *.div_cur_state $path]} {
        if {$mode eq "wrong_stage"} {return 5}
        if {$mode eq "unknown"} {return "4'dx"}
        return "4'd6"
    }
    if {$mode eq "invalid"} {return 0}
    return 1
}
proc force {path value option} {
    global deposits reset
    if {$path ne "ara_tb.rst_n" || $option ne "-deposit"} {error "DUT force"}
    lappend deposits [list $path $value $option]
    set reset $value
    puts "MOCK_FORCE $path $value $option"
}
proc run {args} {
    global armed armed_command edge mode reset
    if {$args eq "-negedge ara_tb.clk"} {
        incr edge
        if {$mode eq "lost_reset"} {set reset 1}
        return
    }
    if {[llength $args]} {error "Unexpected advancement"}
    if {$armed} {
        set armed 0
        if {$mode ne "unreached"} {uplevel #0 $armed_command}
    } else {puts "MOCK_RECOVERY edges=$edge"}
}
source {HELPER}
if {[catch {CALL} message]} {puts stderr "ETBR_ERROR $message"; exit 1}
'''.replace('MODE', mode).replace('HELPER', str(m.TCL))
        invocation = 'etbr_execute %s {%s} %d {%s}'%(t['route'], t['stage'], t['code'], ' '.join(t['valids']))
        script = script.replace('CALL', call or invocation)
        return subprocess.run(['tclsh'], input=script, text=True, capture_output=True)

    def test_currentstage_armed_future_edge_fourcycles(self):
        r = self.mock(); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count('MOCK_FORCE '), 2)
        self.assertIn('MOCK_RECOVERY edges=4', r.stdout)
        self.assertEqual(sum(x.startswith('ETBR_LOW_EDGE ') for x in r.stdout.splitlines()), 4)
        self.assertIn('ETBR_TARGET fixture_EX2 ara_tb.dut.ctrl.div_cur_state 6', r.stdout)
        self.assertNotIn('-freeze', m.TCL.read_text())

    def test_unreached_never_drives_pin(self):
        r = self.mock('unreached'); self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('MOCK_FORCE', r.stdout)

    def test_wrong_unknown_or_invalid_stage_never_drives(self):
        for mode in ('wrong_stage', 'unknown', 'invalid'):
            r = self.mock(mode); self.assertNotEqual(r.returncode, 0, mode)
            self.assertNotIn('MOCK_FORCE', r.stdout)

    def test_drive_whitelist_and_values(self):
        for call in ('etbr_deposit ara_tb.dut.ctrl.div_cur_state 0', 'etbr_deposit ara_tb.clk 0',
                     'etbr_deposit ara_tb.rst_n 2'):
            r = self.mock(call=call); self.assertNotEqual(r.returncode, 0)
            self.assertNotIn('MOCK_FORCE', r.stdout)

    def test_reset_lost_is_failure_not_recovery(self):
        r = self.mock('lost_reset'); self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('ETBR_RELEASE', r.stdout)

    def test_injection_and_duplicate_paths(self):
        for call in ('etbr_execute bad {ara_tb.dut.ctrl;force} 6 {ara_tb.dut.busy}',
                     'etbr_execute bad ara_tb.dut.stage 6 {ara_tb.dut.stage}',
                     'etbr_execute bad ara_tb.dut.stage 6 {}'):
            r = self.mock(call=call); self.assertNotEqual(r.returncode, 0)
            self.assertNotIn('MOCK_FORCE', r.stdout)

    def test_anchored_markers_echo_is_not_evidence(self):
        r = self.mock(); self.assertEqual(r.returncode, 0)
        t = self.config(); m.markers(r.stdout, t)
        echoed = 'puts "ETBR_ERROR source echo"\n'+r.stdout
        m.markers(echoed, t)
        for bad in (r.stdout+'ETBR_ERROR actual failure\n', r.stdout+r.stdout,
                    r.stdout.replace('ETBR_LOW_EDGE fixture_EX2 4\n', ''),
                    'puts "ETBR_TARGET fixture_EX2 ara_tb.dut.ctrl.div_cur_state 6"\n'):
            with self.assertRaises(ValueError): m.markers(bad, t)

    def test_actual_preflight_slot0_code6_no_automatic_reset(self):
        pre = m.life.read_bound(m.PRE/'preflight.json', m.PRE_SHA)
        t = m.target(pre); self.assertEqual(t['code'], 6)
        self.assertIn('.gen_lanes[0].', t['stage']); self.assertIn('.gen_num_lanes[0].', t['stage'])
        cmd = m.command()
        self.assertFalse(any(x.startswith('+ARA_UVM_RESET_') for x in cmd))
        self.assertIn('+PRELOAD='+str(m.PRE/'input.elf'), cmd)
        bad = copy.deepcopy(t); bad['stage'] += ';force'
        with self.assertRaises(ValueError): m.entry(bad)


if __name__ == '__main__': unittest.main()
