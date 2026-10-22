"""Complete host GUI stubs; synthetic native IDs are never real DVE evidence."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import lzc_selector_native_product_batch_v5_prepare as v5
from test_lzc_selector_native_product_audit_visibility import MOCK

OUT = v5.batch.product.OUT
PREVIOUS = OUT / 'lzc_selector_native_product_batch-707-20261006-04'
PLAN = json.loads((PREVIOUS / 'batch-plan.json').read_bytes())

NATIVE = r'''
set loads 0
set calls 0
set resets 0
set fixture_active {}
set fixture_original {}
set native_args {}
proc gui_open_cov {args} {incr ::loads}
proc gui_cov_show_cond_ids {args} {}
proc fixture_key {listname} {
    if {$listname eq "branch"} {return [list $::fixture_scope branch [lindex $::selected(branch) 0]]}
    return [list $::fixture_scope vector [lindex $::selected(cond) 0] [lindex $::selected(vector) 0]]
}
proc gui_exclude_items {args} {
    incr ::calls
    set ::native_args $args
    set ::fixture_active [fixture_key [lindex $args 3]]
    set ::fixture_original $::fixture_active
    if {$::failure eq "native"} {error STUB_NATIVE_FAILURE_AFTER_STATE_CHANGE}
}
proc gui_exclusion {args} {
    if {[lindex $args 0] eq "-reset"} {set ::fixture_active {}; incr ::resets; return}
    if {[lsearch -exact $args -excluded] >= 0} {
        return [expr {$::fixture_active ne "" && $::fixture_active eq [fixture_key [lindex $args 3]]}]
    }
}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args 2] 0]
    if {[lindex $args 0] eq "-load"} {
        set ::fixture_active $::fixture_original
        if {$::failure eq "reload"} {error STUB_RELOAD_FAILURE_AFTER_STATE_CHANGE}
        return
    }
    set stream [open $path w]
    if {$::fixture_active ne ""} {
        set target [lindex $::lpb_targets 0]
        puts $stream "CHECKSUM: \"3250293308 [lindex $target 5]\""
        puts $stream "INSTANCE: [lindex $target 2]"
        set vector 1
        if {$::failure eq "signature"} {set vector 0}
        # Deliberately synthetic IDs, distinct from XML and calibration IDs.
        puts $stream "Condition 997 \"[lindex $target 6]\" \"[lindex $target 4] 1 -1\" (998 \"$vector\")"
        puts $stream "ANNOTATION: \"[lindex $::native_args 6]\""
    }
    close $stream
}
proc gui_exit {args} {set ::exited 1}
'''


class SmokeStubTests(unittest.TestCase):
    def execute(self, output, failure='none'):
        candidate = PLAN['targets'][0]['candidate']
        selection = output / 'unit-selection.tcl'
        selection.write_text('set lpq_scope ' + v5.tcl_word(candidate['scope']) + '\nset lpq_output ' + v5.tcl_word(output) + '\n')
        data = MOCK.replace('set mode [lindex $args 3]', 'set mode [lindex $args 3]\n    set ::fixture_scope [lindex $args 4]')
        data += NATIVE + '\nset failure ' + failure + '\n'
        environment = dict(PLAN['environment'], LZC_SELECTOR_NATIVE_PROBE_SELECTION=str(selection))
        for name, value in environment.items():
            data += 'set env(' + name + ') ' + v5.tcl_word(value) + '\n'
        data += 'source ' + v5.tcl_word(v5.PROBE) + r'''
lpd_require [expr {$loads == 1 && $calls == 1 && $resets >= 1 && $fixture_active eq "" &&
    !$lpn_global_before_complete && !$lpq_ready && $lpq_injected == 0}] "Smoke state/cleanup invariant failed"
lpd_require [expr {[llength $native_args] == 7 && [lindex $native_args 6] eq {Native singleton smoke only; {spaces braces} [set ::lpq_injected 1] $not_a_variable}}] "Annotation not forwarded literally"
'''
        wrapped = 'if {[catch {\n' + data + '\n} message]} {puts stderr "$message\n$::errorInfo"; exit 1}\n'
        result = subprocess.run(['tclsh'], input=wrapped, text=True, capture_output=True, cwd=output, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (output / 'DVEfiles').mkdir()
        (output / 'DVEfiles/dve_gui.log').write_text(result.stdout)
        return result.stdout

    def test_complete_five_stages_literal_payload_signature_roundtrip_finalreset(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_smoke_stub-') as temp:
            output = Path(temp)
            self.execute(output)
            result = v5.verify_probe(output, dict(scope=PLAN['targets'][0]['candidate']['scope'], target=PLAN['targets'][0]), PLAN)
            self.assertEqual(result['qualified_candidates'], 0)
            self.assertFalse(result['global4200_same_session_qualification'])
            self.assertTrue(result['final_reset_empty'])
            self.assertEqual(result['same_session_scope_audits'], 5)
            self.assertEqual((output / 'first.el').read_bytes(), (output / 'second.el').read_bytes())

    def test_native_failure_after_state_change_cleans_up_and_never_qualifies(self):
        self.check_failure('native')

    def test_false_signature_rejected_and_finalreset_runs(self):
        self.check_failure('signature')

    def test_reload_failure_after_state_change_finalreset_runs(self):
        self.check_failure('reload')

    def check_failure(self, failure):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_smoke_fail_stub-') as temp:
            output = Path(temp)
            log = self.execute(output, failure)
            self.assertIn('LZC_NATIVE_GUARD_SMOKE_FAILED', log)
            self.assertEqual((output / 'final-empty.el').read_bytes(), b'')
            self.assertEqual(v5.batch.audit(output / 'final.tsv', PLAN['protection_rows'], -1,
                                          PLAN['targets'][0]['candidate']['scope']), 84)
            with self.assertRaises(ValueError):
                v5.verify_probe(output, {}, {})


if __name__ == '__main__':
    unittest.main()
