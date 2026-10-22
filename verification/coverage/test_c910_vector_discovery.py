"""Bounded host/Tcl tests only; fixtures are not evidence of native GUI capability."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import c910_vector_discovery as m

FIXTURE = r'''
set vd_host_test_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set vd_scope scope0
set vd_test sample0
set mode %s
set clicks 0
set selected {}
proc entries {} {
    global clicks mode
    if {$mode eq "global"} {
        if {$clicks %% 2} {return [list {ID zero} "ID one\nraw line" {remainder compact}]}
        return [list {initial_divisor_in[55:0]} {initial_remainder_in[60:0]}]
    }
    if {$clicks == 0} {return [list {initial_divisor_in[55:0]} {initial_remainder_in[60:0]}]}
    if {$clicks == 1} {return [list {D bit zero} {D bit one} {initial_remainder_in[60:0]}]}
    if {$clicks == 2} {return [list {D bit zero} {D bit one} {R bit zero} {R bit one}]}
    return [list {initial_divisor_in[55:0]} {R bit zero} {R bit one}]
}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_get_selected {args} {
    global selected
    if {[lsearch -exact $args -count] >= 0} {return [llength $selected]}
    return $selected
}
proc gui_list_select {args} {
    global selected
    if {[lsearch -exact $args -unselect] >= 0} {set selected {}} else {set selected [lindex $args end]}
    return {}
}
proc gui_cov_tgl_double_click {args} {global clicks; incr clicks; return native_return}
proc gui_process_events {args} {return event_return}
proc gui_list_get_property {args} {
    set c [lindex $args end]
    if {$c >= 4} {error column_end}
    return [lindex {Variable Type Coverage Display} $c]
}
proc gui_list_get {args} {
    set rows [entries]
    set item [lindex $args end]
    foreach key {path meta firstChild nextSibling text} {
        if {[lsearch -exact $args -$key] >= 0} {set op $key; break}
    }
    if {$op eq "firstChild"} {
        if {$item eq "-firstChild"} {return h0}
        return 0
    }
    set n [string range $item 1 end]
    if {$op eq "nextSibling"} {
        incr n
        if {$n >= [llength $rows]} {return 0}
        return h$n
    }
    if {$op eq "path"} {return "raw path $n"}
    if {$op eq "meta"} {return "raw meta $n"}
    set c [lindex $args [expr {[lsearch -exact $args -text] + 1}]]
    if {$c == 0} {return [lindex $rows $n]}
    if {$c == 1} {return port}
    if {$c == 2} {return 0.00%%}
    return "\tfull display\nreturnvalue"
}
vd_capture initial [list setup_only]
vd_capture click1 [vd_click {initial_divisor_in[55:0]}]
vd_capture click2 [vd_click {initial_remainder_in[60:0]}]
vd_capture click3_restore_probe [vd_click {initial_divisor_in[55:0]}]
set f [open [file join $env(DVE_COVERAGE_OUTPUT) discovery-done.txt] w]
puts $f C910_SINGLE_SCOPE_DISCOVERY_DONE_NOT_QUALIFICATION
close $f
'''


class Discovery(unittest.TestCase):
    def fixture(self, out, mode='global'):
        script = FIXTURE % (m.TCL, out, mode)
        r = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, '')
        return dict(scope='scope0', test='sample0')

    def test_global_fixture_distinguishes_after_first_and_second_click(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            counts = m.capture_gate(out, self.fixture(out))
            self.assertEqual(list(counts.values()), [2, 3, 2, 3])
            raw = m.frames(out / 'click1.frames')
            self.assertEqual(sum(r[0] == 'rawrow' for r in raw), 3)
            self.assertIn('raw line', (out / 'click1.frames').read_text())
            self.assertTrue(any(r[0] == 'column' and 'column_end' in r[2] for r in raw))

    def test_local_and_noncanonical_labels_never_regex_filtered(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            counts = m.capture_gate(out, self.fixture(out, 'local'))
            self.assertEqual(list(counts.values()), [2, 3, 4, 3])
            self.assertIn('R bit zero', (out / 'click2.frames').read_text())

    def test_missing_stage_native_error_and_sample_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            c = self.fixture(out)
            with self.assertRaises(ValueError):
                m.capture_gate(out, dict(c, scope='foreign'))
            (out / 'discovery-error.txt').write_text('native failed')
            with self.assertRaises(ValueError):
                m.capture_gate(out, c)
            (out / 'discovery-error.txt').unlink()
            (out / 'click2.frames').unlink()
            with self.assertRaises(FileNotFoundError):
                m.capture_gate(out, c)

    def test_truncation_malformed_framing_and_empty_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.frames'
            for data in (b'', b'bad\nabc\n', b'20\nabc\n', b'3\nabc!'):
                p.write_bytes(data)
                with self.assertRaises(ValueError):
                    m.frames(p)

    def test_no_EL_operations_or_regex_in_capture_and_only_one_open(self):
        text = m.TCL.read_text()
        for forbidden in ('regexp', 'gui_exclusion', 'qc_reset', 'qc_save', 'mq_load', 'soc_audit'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(text.count('gui_open_cov '), 1)
        self.assertEqual(text.count('p740_root\n'), 1)
        self.assertEqual(text.count('vd_capture click'), 3)

    def test_fixed_interpreter_no_collect300_and_persistent_logs(self):
        c = dict(launch_contract=dict(unit='one', pythonpath='/host', host_tools=[dict(path=p) for p in
                 ('/usr/bin/systemd-run', '/usr/bin/systemctl', '/usr/bin/python3.9')]))
        cmd = m.service_command(c, Path('/output'), 'a' * 64)
        self.assertIn('--property=RuntimeMaxSec=290', cmd)
        self.assertIn('--property=TimeoutStopSec=10', cmd)
        self.assertNotIn('--property=RuntimeMaxSec=900', cmd)
        self.assertNotIn('--collect', cmd)
        self.assertIn('--property=Restart=no', cmd)
        self.assertIn('--property=StandardError=append:/output/service-stderr.log', cmd)
        self.assertIn('--property=StandardOutput=append:/output/service-stdout.log', cmd)
        self.assertEqual(cmd[cmd.index('/usr/bin/python3.9') + 2], str(m.SCRIPT))

    def test_bad_review_and_retry_never_start_process(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            with patch.object(m.subprocess, 'run') as run, patch.object(m, 'check', return_value={}):
                with self.assertRaises(ValueError):
                    m.launch(out, 'a' * 64, 'b' * 64)
                (out / 'service-request.json').write_text('{}')
                with self.assertRaises(ValueError):
                    m.launch(out, 'a' * 64, 'a' * 64)
                run.assert_not_called()

    def test_precheck_error_records_terminal1_and_no_EDA(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            with patch.object(m, 'check', side_effect=ValueError('precheck')), \
                 patch.object(m.subprocess, 'Popen') as native:
                with self.assertRaises(ValueError):
                    m.worker(out, 'a' * 64, 'a' * 64)
                native.assert_not_called()
            for name in ('worker-error.json', 'terminal.json'):
                row = json.loads((out / name).read_text())
                self.assertEqual(row['returncode'], 1)
                self.assertFalse(row['EDA_started'])
                self.assertEqual(row['phase'], 'precheck')

    def test_foreign_scope_multiple_instances_and_changed_bound_rejected(self):
        out = Path('/host/out')
        origin = dict(instances=[dict(scope='scope0')], test='sample0', design='design0', vdb='vdb0', identity={})
        c = dict(schema='C910_VECTOR_UI_DISCOVERY_V1', output=str(out), timeout_seconds=300,
                 automatic_retry=False, read_only=True, qualification=False, pins={},
                 scope='scope0', instances=origin['instances'], **{k: origin[k] for k in ('test', 'design', 'vdb', 'identity')})
        for changes in (dict(scope='scope1'), dict(instances=[{}, {}]), dict(timeout_seconds=301),
                        dict(read_only=False), dict(qualification=True), dict(test='sample1')):
            with patch.object(m.life, 'read_bound', side_effect=[dict(c, **changes), origin]), \
                 patch.object(m.life, 'check'):
                with self.assertRaises(ValueError):
                    m.check(out, 'a' * 64)

    def test_native0_verify_failure_is_recorded_not_completed(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            seal = 'a' * 64
            group = '0::/user.slice/user-1000.slice/user@1000.service/app.slice/discovery.service\n'
            c = dict(identity={}, launch_contract=dict(unit='discovery', uid=1000, pythonpath='/host',
                host_tools=[dict(path=p) for p in ('/usr/bin/systemd-run', '/usr/bin/systemctl', '/usr/bin/python3.9')]))
            (out / 'service-request.json').write_text(json.dumps(dict(command=m.service_command(c, out, seal), reviewed_seal=seal)))
            (out / 'service-launch-receipt.json').write_text('{}')
            proc = Mock(pid=2222, returncode=0)
            with patch.object(m, 'check', return_value=c), patch.object(m, 'proc_cgroup', return_value=group), \
                 patch.object(m.tools, 'controlled_environment', return_value={}), \
                 patch.object(m.tools, 'process_info', return_value=dict(starttime=100)), \
                 patch.object(m.core.ptw, 'command', return_value=['/sealed/native']), \
                 patch.object(m, 'observe', return_value=[dict(pid=3333)]), \
                 patch.object(m, 'verify', side_effect=ValueError('raw tree incomplete')), \
                 patch.object(m.subprocess, 'Popen', return_value=proc), patch.dict(os.environ, C1424_CONFIG_SEAL=seal):
                with self.assertRaisesRegex(ValueError, 'raw tree incomplete'):
                    m.worker(out, seal, seal)
            self.assertEqual(json.loads((out / 'terminal.json').read_text())['returncode'], 0)
            error = json.loads((out / 'worker-error.json').read_text())
            self.assertEqual(error['returncode'], 1)
            self.assertEqual(error['native_returncode'], 0)
            self.assertEqual(error['phase'], 'verify')
            self.assertFalse((out / 'discovery-result.json').exists())

    def test_boolean_nonzero_timeout_terminal_never_complete(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            for name in ('execution.json', 'live-identity.json'):
                (out / name).write_text('{}' if name == 'execution.json' else '[{}]')
            with patch.object(m, 'check', return_value={}):
                for rc, timeout in ((False, False), (1, False), (0, True)):
                    (out / 'terminal.json').write_text(json.dumps(dict(returncode=rc, timeout=timeout, actual_dve=[{}])))
                    with self.assertRaises(ValueError):
                        m.verify(out, 'a' * 64)
            self.assertFalse((out / 'discovery-result.json').exists())

    def test_tree_and_column_query_errors_retained_not_silently_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            script = FIXTURE % (m.TCL, out, 'global')
            setup = script.split('vd_capture initial')[0]
            extra = '''
rename gui_list_get original_get
proc gui_list_get {args} {if {[lsearch -exact $args -firstChild] >= 0} {error navigation_failure}; return [eval original_get $args]}
catch {vd_capture initial [list setup_only]} message
puts $message
'''
            r = subprocess.run(['tclsh'], input=setup + extra, capture_output=True, text=True, timeout=10)
            self.assertIn('Raw root query failed', r.stdout)
            records = m.frames(out / 'initial.frames')
            self.assertTrue(any(r[0] == 'root' and 'navigation_failure' in r[1] for r in records))
            self.assertEqual(records[-1][1], '1')


if __name__ == '__main__':
    unittest.main()
