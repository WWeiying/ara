from pathlib import Path
import subprocess
import unittest

import lzc_selector_native_seven_policy_runtime_v3 as subject

ROOT = subject.frozen.OUT / 'lzc-selector-native-seven-policy-runtime-v2-724-parent-20261006-01'
VISIBILITY = Path(subject.prior.__file__).with_name('lzc_selector_native_product_audit_visibility.tcl')


def tcl(text):
    result = subprocess.run(['/usr/bin/tclsh'], input=text, text=True, capture_output=True, check=True)
    if result.stderr:
        raise AssertionError(result.stderr)
    return result.stdout


class ScopeTests(unittest.TestCase):
    def test_exact_one_declaration_only(self):
        subject.check_scope_adapter()
        self.assertEqual(subject.TCL.read_bytes(), subject.serialization_prior.TCL.read_bytes().replace(
            subject.OLD.encode(), subject.NEW.encode(), 1))

    def script(self, declaration):
        return '''
proc init {} {
    %s
    source {%s}
    source {%s}
    if {[array size lpa_binding] != 1200 || [array size lpa_expected] != 36} {error "Incomplete binding"}
}
init
set branches 0
set missing 0
set mismatch 0
foreach row $seven_rows {
    if {[lindex $row 1] ne "branch"} {continue}
    incr branches
    set pos [lindex $row 5]
    if {![info exists lpa_binding($pos)]} {incr missing;continue}
    set b $lpa_binding($pos)
    if {[lindex $b 0] ne [lindex $row 0] || [lindex $b 3] ne [lindex $row 2] || [lindex $b 4] ne [lindex $row 4]} {incr mismatch}
}
puts "$branches $missing $mismatch [llength $seven_rows] [llength $seven_target_positions]"
''' % (declaration, VISIBILITY, ROOT/'seven-selection.tcl')

    def test_proc_scope_actual1200_36_and4200_60(self):
        out=tcl(self.script('global seven_rows seven_target_positions lpa_binding lpa_expected')+
                'puts [array size lpa_expected]\n')
        self.assertEqual(out.splitlines(), ['1200 0 0 4200 60','36'])

    def test_frozen_local_scope_reproduces1200_missing(self):
        out=tcl(self.script('global seven_rows seven_target_positions')+
                'puts [catch {lpb_row [lindex $seven_rows 0]} message]\nputs $message\n')
        self.assertEqual(out.splitlines(), ['1200 1200 0 4200 60','1',
                                          'No discovery-backed native token for protected branch position'])

    def test_missing_tuple_and_wrong_tuple_rejected_before_gui(self):
        text=self.script('global seven_rows seven_target_positions lpa_binding lpa_expected')+'''
unset lpa_binding(0)
puts [catch {lpb_row [lindex $seven_rows 0]} message]
puts $message
set lpa_binding(0) [list WRONG Item0 Branch0.0 0 0]
puts [catch {lpb_row [lindex $seven_rows 0]} message]
puts $message
'''
        self.assertEqual(tcl(text).splitlines()[1:], ['1','No discovery-backed native token for protected branch position',
                                                    '1','Protected position/discovery identity differs'])


if __name__ == '__main__': unittest.main()
