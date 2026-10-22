"""Offline successor contracts and simulated full-audit gate; no DVE launch."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import lzc_selector_native_product_batch_v3 as v3

OUT = v3.batch.product.OUT
PREVIOUS = OUT / 'lzc_selector_native_product_batch-707-20261006-02'
DIAGNOSIS = OUT / 'lzc_selector_native_product_audit_visibility-707-20261006-01'


class BatchV3Tests(unittest.TestCase):
    def run_tcl(self, body):
        data = 'set lpn_test_only 1\nproc gui_open_cov {args} {error "Forbidden DVE launch"}\n'
        data += 'source ' + v3.batch.tcl_word(v3.SCRIPT) + '\n' + body
        wrapped = 'if {[catch {\n' + data + '\n} msg]} {puts stderr "$msg\n$::errorInfo"; exit 1}\n'
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_gate_unit-') as temp:
            result = subprocess.run(['tclsh'], input=wrapped, text=True, capture_output=True, timeout=10, cwd=temp)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_prepare_preserves_all_targets_inputs_protection_and_budget(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_batch_v3_unit-') as temp:
            output = Path(temp)
            output.rmdir()
            with mock.patch.object(v3.subprocess, 'Popen') as launch:
                v3.prepare(PREVIOUS, DIAGNOSIS, output)
                plan = v3.reviewed_plan(output)
                launch.assert_not_called()
            old = json.loads((PREVIOUS / 'batch-plan.json').read_bytes())
            self.assertEqual(plan['targets'], old['targets'])
            self.assertEqual(plan['protection_rows'], old['protection_rows'])
            self.assertEqual(plan['command'][2], '10500s')
            self.assertEqual(plan['command'][-1], str(v3.SCRIPT))
            self.assertEqual(plan['visibility_successor']['watchdog_seconds'], 10530)
            self.assertEqual((output / 'selection.tcl').read_text().partition('\n')[2],
                             (PREVIOUS / 'selection.tcl').read_text().partition('\n')[2])
            self.assertEqual((output / 'native-bindings.tcl').read_bytes(),
                             (DIAGNOSIS / 'native-bindings.tcl').read_bytes())
            self.assertFalse((output / 'reviewed-start.json').exists())
            # Re-sealing a plan with the old script still fails the new identity validator.
            plan['command'][-1] = str(v3.batch.SCRIPT)
            (output / 'batch-plan.json').write_text(json.dumps(plan))
            (output / 'batch-plan.sha256.json').write_text(json.dumps({
                str(output / 'batch-plan.json'): v3.sha(output / 'batch-plan.json')}))
            with self.assertRaises(ValueError):
                v3.reviewed_plan(output)

    def test_full_gate_allows_only_after4200_audit_rows(self):
        self.run_tcl(r'''
set lpb_output [pwd]
set mutations 0
proc lpn_native_exclude {args} {incr ::mutations}
lpd_require [catch {lpn_guard_exclude}] "Early singleton admitted"
rename lpn_visibility_audit original_audit
proc lpn_visibility_audit {path rows active} {
    set stream [open $path w]
    puts $stream header
    foreach row $rows {puts $stream audited}
    close $stream
}
set stream [file tempfile path [file join [pwd] lzc-selector-gate]]
close $stream
set lpb_output [file dirname $path]
set initial [file join $lpb_output global-before.tsv]
lpb_audit $initial [lrepeat 4200 row] -1
lpd_require $lpn_global_before_complete "Full audit not admitted"
lpn_guard_exclude
lpd_require [expr {$mutations == 1}] "Wrong mutation count"
file delete $initial $path
''')

    def test_partial_or_failed_audit_never_enables_singleton(self):
        self.run_tcl(r'''
set stream [file tempfile path [file join [pwd] lzc-selector-gate]]
close $stream
set lpb_output [file dirname $path]
set initial [file join $lpb_output global-before.tsv]
set mutations 0
proc lpn_native_exclude {args} {incr ::mutations}
rename lpn_visibility_audit original_audit
proc lpn_visibility_audit {path rows active} {
    set stream [open $path w]
    puts $stream header
    puts $stream row0
    puts $stream row1
    close $stream
}
foreach count {2 4200} {
    set lpn_global_before_complete 1
    lpd_require [catch {lpb_audit $initial [lrepeat $count row] -1}] "Partial audit admitted"
    lpd_require [catch {lpn_guard_exclude}] "Partial audit allowed mutation"
}
rename lpn_visibility_audit partial_audit
proc lpn_visibility_audit {args} {error "Branch1.0 not found"}
lpd_require [catch {lpb_audit $initial [lrepeat 4200 row] -1}] "Failure admitted"
lpd_require [catch {lpn_guard_exclude}] "Failure allowed mutation"
lpd_require [expr {$mutations == 0}] "Unexpected singleton"
file delete $initial $path
''')

    def test_bindings_load_before_one_session_and_exclusion_guard_installed(self):
        binding = v3.batch.tcl_word(DIAGNOSIS / 'native-bindings.tcl')
        self.run_tcl('set env(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS) ' + binding + r'''
set sessions 0
set mutations 0
proc gui_exclude_items {args} {incr ::mutations}
rename lpb_session frozen_session
proc lpb_session {} {
    incr ::sessions
    lpd_require [expr {[array size ::lpa_binding] == 1200 && [array size ::lpa_expected] == 36}] "Bindings not loaded"
    lpd_require [catch {gui_exclude_items}] "Guard not installed before session"
}
lpn_session
lpd_require [expr {$sessions == 1 && $mutations == 0}] "Wrong session/mutation count"
''')

    def test_successor_markers_required_in_addition_to_frozen_verifier(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_verifier_unit-') as temp:
            output = Path(temp)
            (output / 'DVEfiles').mkdir()
            log = output / 'DVEfiles/dve_gui.log'
            good = 'LZC_NATIVE_BATCH_V3_VISIBILITY_BINDINGS_LOADED\nLZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE\n'
            with mock.patch.object(v3.batch, 'verify', return_value={'status': 'fixture-only'}) as frozen:
                for data in ('', good + good):
                    log.write_text(data)
                    with self.assertRaises(ValueError):
                        v3.verify(output, {})
                log.write_text(good)
                result = v3.verify(output, {})
                self.assertEqual(result['actual_script_sha256'], v3.sha(v3.SCRIPT))
                self.assertEqual(frozen.call_count, 3)

    def test_real_failed02_partial_audit_rejected_by_frozen_verifier(self):
        plan = json.loads((PREVIOUS / 'batch-plan.json').read_bytes())
        with self.assertRaises(ValueError):
            v3.batch.verify(PREVIOUS, plan)

    def test_library_and_entry_have_no_extra_design_load_or_final_apply(self):
        source = v3.SCRIPT.read_text()
        self.assertNotIn('gui_open_cov ', source)
        self.assertIn('if {![info exists lpn_test_only]}', source)
        self.assertIn('global-final.tsv', source)
        self.assertIn('gui_exclusion -reset', source)
        self.assertEqual(v3.batch.SCRIPT.read_text().count('gui_open_cov '), 1)


if __name__ == '__main__':
    unittest.main()
