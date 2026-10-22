"""Offline builtin-protection simulation and immutable singleton contracts."""
import json
from pathlib import Path
import subprocess
import tempfile
import tkinter
import unittest
from unittest import mock

import lzc_selector_native_product_batch_v4 as v4

OUT = v4.batch.product.OUT
PREVIOUS = OUT / 'lzc_selector_native_product_batch-707-20261006-03'

# An alias stands in for the native builtin. Reject renaming any GUI command,
# while allowing owned helper renames used by the visibility library.
PROTECTED_GUI = r'''
set loads 0
set mutations 0
set native_args {}
proc fixture_exclude {args} {
    incr ::mutations
    set ::native_args $args
    return NATIVE_RESULT
}
interp alias {} gui_exclude_items {} fixture_exclude
proc gui_open_cov {args} {incr ::loads; error SIMULATED_STOP_AFTER_LOAD}
rename rename fixture_rename
proc rename {old new} {
    if {[string match gui_* $old]} {error {EK-CMD-013 command cannot be renamed}}
    fixture_rename $old $new
}
set native_identity [interp alias {} gui_exclude_items]
'''


class BatchV4Tests(unittest.TestCase):
    def run_tcl(self, body, entry=None):
        entry = entry or v4.SCRIPT
        data = PROTECTED_GUI + '\nset lpn_test_only 1\nset lpn_v4_test_only 1\n'
        data += 'source ' + v4.tcl_word(entry) + '\n' + body
        wrapper = 'if {[catch {\n' + data + '\n} msg]} {puts stderr "$msg\n$::errorInfo"; exit 1}\n'
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_v4_tcl_unit-') as temp:
            result = subprocess.run(['tclsh'], input=wrapper, text=True, capture_output=True, cwd=temp, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_session_body_diff_is_exactly_one_call(self):
        parser = tkinter.Tcl()
        parser.eval('set lpb_test_only 1\nsource ' + v4.tcl_word(v4.batch.SCRIPT))
        original = parser.eval('info body lpb_session')
        text, change = v4.guarded_session()
        parser.eval(text)
        actual = parser.eval('info body lpb_session')
        self.assertEqual(actual, original.replace(v4.CALL, v4.GUARDED_CALL, 1))
        self.assertEqual(actual.count('lpn_guard_exclude'), 1)
        self.assertNotIn('gui_exclude_items', actual)
        self.assertEqual(actual.count('gui_open_cov '), 1)
        self.assertEqual(change['substitutions'], 1)
        self.assertTrue(change['all_other_body_bytes_identical'])

    def test_protected_builtin_reproduces03_failure_before_design_load(self):
        self.run_tcl('set env(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS) ' +
                     v4.tcl_word(PREVIOUS / 'native-bindings.tcl') + r'''
lpd_require [catch {lpn_session} msg] "v3 unexpectedly accepted protected rename"
lpd_require [string match {*EK-CMD-013*} $msg] "Wrong v3 failure"
lpd_require [expr {$loads == 0 && $mutations == 0}] "v3 reached design/exclusion"
lpd_require [expr {[interp alias {} gui_exclude_items] eq $native_identity}] "Builtin identity changed"
''', entry=v4.v3.SCRIPT)

    def test_v4_reaches_original_design_load_without_renaming_builtin(self):
        text, _ = v4.guarded_session()
        # Store only the new session copy inside the isolated test directory.
        encoded = '[encoding convertfrom utf-8 [binary decode hex ' + text.encode().hex() + ']]'
        self.run_tcl('set text ' + encoded + r'''
set session [file join [pwd] guarded-session.tcl]
set stream [open $session w]
puts -nonewline $stream $text
close $stream
set env(LZC_SELECTOR_NATIVE_GUARDED_SESSION) $session
''' + 'set env(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS) ' + v4.tcl_word(PREVIOUS / 'native-bindings.tcl') + '\n' +
                     'set env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION) ' +
                     v4.tcl_word(Path(json.loads((PREVIOUS / 'batch-plan.json').read_bytes())[
                         'environment']['LZC_SELECTOR_NATIVE_PRODUCT_SELECTION'])) + '\n' +
                     'set env(LZC_SELECTOR_NATIVE_BATCH_SELECTION) ' + v4.tcl_word(PREVIOUS / 'selection.tcl') + r'''
lpd_require [catch {lpn_session} msg] "Expected mocked stop missing"
lpd_require [expr {$msg eq "SIMULATED_STOP_AFTER_LOAD" && $loads == 1 && $mutations == 0}] "v4 did not reach exact one load"
lpd_require [expr {[interp alias {} gui_exclude_items] eq $native_identity}] "Builtin changed"
lpd_require [catch {rename gui_exclude_items anything}] "Protection simulation inactive"
''')

    def test_guard_calls_original_builtin_only_after_full4200_gate(self):
        self.run_tcl(r'''
lpd_require [catch {lpn_guard_exclude -id CovDetail.1 -list branch -selected}] "Early exclude admitted"
set lpb_output [pwd]
rename lpn_visibility_audit original_audit
proc lpn_visibility_audit {path rows active} {
    set stream [open $path w]
    puts $stream header
    foreach row $rows {puts $stream audited}
    close $stream
}
lpb_audit [file join $lpb_output global-before.tsv] [lrepeat 4200 row] -1
set result [lpn_guard_exclude -id CovDetail.1 -list branch -selected]
lpd_require [expr {$result eq "NATIVE_RESULT" && $mutations == 1 &&
    $native_args eq {-id CovDetail.1 -list branch -selected}}] "Native call arguments/return differ"
lpd_require [expr {[interp alias {} gui_exclude_items] eq $native_identity}] "Builtin changed"
''')

    def test_partial_and_failed_audit_keep_original_builtin_uncalled(self):
        self.run_tcl(r'''
set lpb_output [pwd]
rename lpn_visibility_audit original_audit
proc lpn_visibility_audit {path rows active} {
    set stream [open $path w]
    puts $stream header
    puts $stream row0
    puts $stream row1
    close $stream
}
foreach count {2 4200} {
    lpd_require [catch {lpb_audit [file join $lpb_output global-before.tsv] [lrepeat $count row] -1}] "Partial audit admitted"
    lpd_require [catch {lpn_guard_exclude}] "Partial audit allowed exclude"
}
rename lpn_visibility_audit partial_audit
proc lpn_visibility_audit {args} {error {Branch1.0 not found}}
lpd_require [catch {lpb_audit [file join $lpb_output global-before.tsv] [lrepeat 4200 row] -1}] "Failed audit admitted"
lpd_require [catch {lpn_guard_exclude}] "Failed audit allowed exclude"
lpd_require [expr {$mutations == 0}] "Builtin called before gate"
''')

    def test_prepare_preserves120_targets4200_rows_bindings_and10500_budget(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_v4_prepare_unit-') as temp:
            output = Path(temp)
            output.rmdir()
            with mock.patch.object(v4.subprocess, 'Popen') as launch:
                v4.prepare(PREVIOUS, output)
                plan = v4.reviewed_plan(output)
                launch.assert_not_called()
            old = json.loads((PREVIOUS / 'batch-plan.json').read_bytes())
            self.assertEqual(plan['targets'], old['targets'])
            self.assertEqual(plan['protection_rows'], old['protection_rows'])
            self.assertEqual(plan['command'][2], '10500s')
            self.assertEqual(plan['command'][-1], str(v4.SCRIPT))
            self.assertEqual((output / 'native-bindings.tcl').read_bytes(), (PREVIOUS / 'native-bindings.tcl').read_bytes())
            self.assertEqual((output / 'budget-review.json').read_bytes(), (PREVIOUS / 'budget-review.json').read_bytes())
            self.assertFalse((output / 'reviewed-start.json').exists())
            plan['command'][-1] = str(v4.v3.SCRIPT)
            (output / 'batch-plan.json').write_text(json.dumps(plan))
            (output / 'batch-plan.sha256.json').write_text(json.dumps({
                str(output / 'batch-plan.json'): v4.sha(output / 'batch-plan.json')}))
            with self.assertRaises(ValueError):
                v4.reviewed_plan(output)

    def test_real03_is_not_qualified_by_frozen_verifier(self):
        plan = json.loads((PREVIOUS / 'batch-plan.json').read_bytes())
        with self.assertRaises(FileNotFoundError):
            v4.batch.verify(PREVIOUS, plan)

    def test_entry_identity_markers_required_beyond_frozen_verifier(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_v4_verify_unit-') as temp:
            output = Path(temp)
            (output / 'DVEfiles').mkdir()
            log = output / 'DVEfiles/dve_gui.log'
            good = 'LZC_NATIVE_BATCH_V4_BUILTIN_PRESERVING_SESSION_LOADED\nLZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE\n'
            with mock.patch.object(v4.batch, 'verify', return_value={'status': 'fixture-only'}):
                for data in ('', good + good):
                    log.write_text(data)
                    with self.assertRaises(ValueError):
                        v4.verify(output, {})
                log.write_text(good)
                self.assertEqual(v4.verify(output, {})['actual_script_sha256'], v4.sha(v4.SCRIPT))


if __name__ == '__main__':
    unittest.main()
