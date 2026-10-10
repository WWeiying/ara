"""Host Tcl tests only; actual DVE parser qualification remains pending."""
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'lzc_selector_native_product_guard_legacy.tcl'
SETUP = r'''
set lpn_global_before_complete 0
set calls 0
set native_args {}
proc lpd_require {ok message} {if {!$ok} {error $message}}
proc gui_exclude_items {args} {incr ::calls; set ::native_args $args; return NATIVE_RESULT}
'''


class LegacyGuardTests(unittest.TestCase):
    def run_tcl(self, body):
        data = SETUP + '\nsource {' + str(SCRIPT) + '}\n' + body
        wrapped = 'if {[catch {\n' + data + '\n} message]} {puts stderr "$message\n$::errorInfo"; exit 1}\n'
        result = subprocess.run(['tclsh'], input=wrapped, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_argument_expansion_builtin_rename_or_auto_run(self):
        source = SCRIPT.read_text()
        for token in ('{*}', 'rename ', 'gui_open_cov', 'gui_exclusion -reset'):
            self.assertNotIn(token, source)
        self.run_tcl('lpd_require [expr {$calls == 0}] "Library mutated native state"')

    def test_closed_gate_preflight_compiles_guard_without_native_call(self):
        self.run_tcl(r'''
set version [lpng_preflight]
lpd_require [expr {$version eq [info patchlevel] && $calls == 0}] "Preflight reached native builtin"
''')

    def test_preflight_rejects_parser_error_and_open_gate(self):
        self.run_tcl(r'''
proc lpn_guard_exclude {args} {error {extra characters after close-brace}}
lpd_require [catch {lpng_preflight} message] "Parser failure accepted"
lpd_require [expr {$message eq "Guard parser/preflight failed before design load"}] "Wrong failure"
set lpn_global_before_complete 1
lpd_require [catch {lpng_preflight} message] "Open gate accepted"
lpd_require [expr {$calls == 0}] "Preflight mutated native state"
''')

    def test_branch_vector_arguments_and_return_match_native_builtin(self):
        self.run_tcl(r'''
set lpn_global_before_complete 1
set annotation {Native singleton measurement only; no final processor exclusion application}
foreach listname {branch vector} {
    set value [lpn_guard_exclude -id CovDetail.1 -list $listname -selected -annotation $annotation]
    lpd_require [expr {$value eq "NATIVE_RESULT" && $native_args eq [list -id CovDetail.1 -list $listname -selected -annotation $annotation]}] "Native arguments/return differ"
}
lpd_require [expr {$calls == 2}] "Wrong native call count"
''')

    def test_wrong_flags_scope_and_arity_rejected(self):
        self.run_tcl(r'''
set lpn_global_before_complete 1
set annotation {Native singleton measurement only; no final processor exclusion application}
foreach bad {
    {-id OtherDetail -list branch -selected -annotation}
    {-id CovDetail.1 -list cond -selected -annotation}
    {-id CovDetail.1 -list branch -all -annotation}
} {
    # List construction preserves words; hostile or unexpected input is never evaluated.
    set result [catch {lpn_guard_exclude [lindex $bad 0] [lindex $bad 1] [lindex $bad 2] [lindex $bad 3] [lindex $bad 4] [lindex $bad 5] $annotation} message]
    lpd_require $result "Unexpected native call admitted"
}
lpd_require [catch {lpn_guard_exclude -id CovDetail.1}] "Wrong arity admitted"
lpd_require [expr {$calls == 0}] "Rejected inputs reached native builtin"
''')

    def test_hostile_annotation_is_one_literal_native_argument(self):
        self.run_tcl(r'''
set lpn_global_before_complete 1
set injected 0
set payloads [list {comment with spaces and {braces}} {bad; incr ::injected} {[incr ::injected] $::injected}]
lappend payloads [format {%c unbalanced} 123]
lappend payloads [format {%c unbalanced} 125]
foreach annotation $payloads {
    set result [lpn_guard_exclude -id CovDetail.1 -list branch -selected -annotation $annotation]
    lpd_require [expr {$result eq "NATIVE_RESULT" && [llength $native_args] == 7 && [lindex $native_args 6] eq $annotation}] "Annotation split or changed"
}
lpd_require [expr {$calls == 5 && $injected == 0 && [lpng_list_preflight] == 5}] "Annotation executed as code"
''')


if __name__ == '__main__':
    unittest.main()
