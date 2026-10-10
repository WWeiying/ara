import json
from pathlib import Path
import subprocess
import unittest

import lzc_selector_native_product_audit_visibility as visibility
from lzc_selector_native_product_inventory import decode_lines

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'out'
DISCOVERY = OUT / 'lzc_selector_native_product_discovery-707-20261006-03'
FAILED = OUT / 'lzc_selector_native_product_batch-707-20261006-02'

# Each action creates a fresh detail view: only Item0 is initially open.
# This models the suspected visibility mechanism, not a new DVE measurement.
MOCK = r'''
set expanded 0
set expansions 0
set parents 12
set mode Branch
set readback exact
array set selected {branch {} cond {} vector {}}
proc gui_open_cov {args} {error "Forbidden DVE launch"}
proc gui_exclude_items {args} {error "Forbidden exclusion"}
proc gui_list_action {args} {
    global expanded mode selected
    set mode [lindex $args 3]
    set expanded 0
    array set selected {branch {} cond {} vector {}}
}
proc gui_covdetail_query {args} {return $::mode}
proc gui_list_expand {args} {
    if {[lindex $args 1] ne "CovDetail.1"} {return}
    if {$::mode ne "Branch"} {error "Condition is not a branch tree"}
    set ::expanded 1
    incr ::expansions
}
proc gui_list_get {args} {
    global parents
    set op [lindex $args 2]
    set node [lindex $args 3]
    if {$op eq "-firstChild" && $node eq ""} {return P0}
    if {[regexp {^P([0-9]+)$} $node unused id]} {
        switch -- $op {
            -path {return Item$id}
            -firstChild {return L$id.0}
            -nextSibling {if {$id + 1 < $parents} {return P[expr {$id+1}]} ; return {}}
        }
    }
    if {[regexp {^L([0-9]+)\.([01])$} $node unused id arm]} {
        switch -- $op {
            -path {return Item$id.Branch$id.$arm}
            -meta {return Branch$id.$arm}
            -childCount {return 0}
            -nextSibling {if {$arm == 0} {return L$id.1} ; return {}}
        }
    }
    error "Unexpected native tree query $args"
}
proc gui_list_select {args} {
    global selected expanded readback
    set listname [lindex $args 3]
    set action [lindex $args 4]
    set name [lindex [lindex $args 5] 0]
    if {$action eq "-unselect"} {set selected($listname) {}; return}
    if {$listname eq "branch"} {
        if {![regexp {^Branch([0-9]+)\.([01])$} $name unused id arm] ||
            $id >= $::parents || (!$expanded && $id != 0)} {
            error "gui_list_select: $name not found"
        }
    }
    set selected($listname) [list $name]
    if {$readback eq "alias"} {set selected($listname) {WRONG}}
    if {$readback eq "multiple"} {set selected($listname) [list $name EXTRA]}
}
proc gui_list_get_selected {args} {
    set listname [lindex $args 3]
    switch -- [lindex $args 4] {
        -count {return [llength $::selected($listname)]}
        -first {return [lindex $::selected($listname) 0]}
        -flat {return $::selected($listname)}
    }
    error "Unexpected selected query $args"
}
proc gui_exclusion {args} {return 0}
'''


class AuditVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((FAILED / 'batch-plan.json').read_bytes())['protection_rows']
        cls.records = decode_lines((DISCOVERY / 'native-inventory.tcllist').read_bytes().decode('latin1'))
        cls.values = visibility.bindings(cls.rows, cls.records)
        scope = cls.values[0]['scope']
        cls.local = [v for v in cls.values if v['scope'] == scope]
        cls.selection = visibility.selection_text(cls.local)
        cls.tcl_rows = '\n'.join(
            'lappend rows [list ' + ' '.join(map(visibility.tcl_word,
                (v['scope'], 'branch', v['logical_native_id'], '', v['vector'], v['position']))) + ']'
            for v in cls.local)

    def run_tcl(self, body, successor=True):
        script = visibility.SCRIPT if successor else HERE / 'lzc_selector_native_product_batch.tcl'
        data = MOCK + '\nset lpb_test_only 1\nsource ' + visibility.tcl_word(script) + '\n'
        data += self.selection + '\nset rows {}\n' + self.tcl_rows + '\n' + body
        # tclsh stdin errors do not reliably set its exit code; catch explicitly.
        wrapped = 'if {[catch {\n' + data + '\n} msg]} {puts stderr "$msg\n$::errorInfo"; exit 1}\n'
        result = subprocess.run(['tclsh'], input=wrapped, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_full_native_provenance_and_protection(self):
        self.assertEqual(len(self.values), 1200)
        self.assertEqual(len(self.rows), 4200)
        self.assertEqual((self.values[2]['native_parent_path'], self.values[2]['native_select_token']),
                         ('Item1', 'Branch1.0'))

    def test_provenance_rejects_xml_substitution_and_raw_mismatch(self):
        rows = json.loads(json.dumps(self.rows))
        rows[2]['native_id'] = '99999'
        with self.assertRaises(ValueError):
            visibility.bindings(rows, self.records)
        records = [list(r) for r in self.records]
        raw = next(r for r in records if r[0] == 'branch')
        raw[5] = 'Branch99999.0'
        with self.assertRaises(ValueError):
            visibility.bindings(self.rows, records)

    def test_frozen_reproduces_exact_two_row_visibility_boundary(self):
        self.run_tcl(r'''
gui_list_expand -id CoverageTable.1 -all {<root>}
set done 0
foreach row $rows {
    if {[catch {lpb_row $row} msg]} {break}
    incr done
}
lpd_require [expr {$done == 2 && [string match {*Branch1.0 not found*} $msg]}] "Boundary not reproduced"
lpd_require [expr {$expansions == 0}] "Unexpected detail expansion"
''', successor=False)

    def test_successor_expands_every_fresh_branch_view(self):
        self.run_tcl(r'''
foreach row $rows {lpb_row $row}
lpd_require [expr {$expansions == 24}] "Every fresh view must expand"
''')

    def test_complete_inventory_rejects_missing_and_extra_parents(self):
        for count in (11, 13):
            with self.subTest(count=count):
                self.run_tcl('set parents ' + str(count) + r'''
lpd_require [catch {lpb_row [lindex $rows 0]} msg] "Inventory change admitted"
lpd_require [string match {*inventory differs*} $msg] "Wrong rejection"
lpd_require [expr {[llength $selected(branch)] == 0}] "Selected before inventory validation"
''')

    def test_position_binding_rejects_identity_mismatch(self):
        self.run_tcl(r'''
set first [lindex $rows 0]
set first [lreplace $first 2 2 999]
lpd_require [catch {lpb_row $first} msg] "Identity mismatch admitted"
lpd_require [string match {*identity differs*} $msg] "Wrong rejection"
lpd_require [expr {$expansions == 0}] "Mismatch reached GUI"
''')

    def test_saved_native_token_rejects_wrong_arm(self):
        self.run_tcl(r'''
set lpa_binding(0) [lreplace $lpa_binding(0) 2 2 Branch0.1]
lpd_require [catch {lpb_row [lindex $rows 0]} msg] "Wrong native arm admitted"
lpd_require [string match {*token/parent binding differs*} $msg] "Wrong rejection"
lpd_require [expr {$expansions == 0}] "Mismatch reached GUI"
''')

    def test_branch_selection_rejects_alias_and_multiple_readback(self):
        for mode in ('alias', 'multiple'):
            with self.subTest(mode=mode):
                self.run_tcl('set readback ' + mode + r'''
lpd_require [catch {lpb_row [lindex $rows 0]} msg] "Readback admitted"
lpd_require [string match {*Exact native selection differs*} $msg] "Wrong rejection"
''')

    def test_condition_listview_no_expand_and_exact_readback(self):
        self.run_tcl(r'''
set condition [list child cond {} {exact selector expression} 1 24]
lpd_require [expr {[lpb_row $condition] eq "vector" && $expansions == 0}] "Condition expanded"
foreach failure {alias multiple} {
    set readback $failure
    lpd_require [catch {lpb_row $condition} msg] "Condition readback admitted"
    lpd_require [string match {*Exact native selection differs*} $msg] "Wrong rejection"
}
''')

    def test_audit_preserves_all_rows_and_resets_validation_each_pass(self):
        self.run_tcl(r'''
set stream [file tempfile path]
close $stream
lpb_audit $path $rows -1
set stream [open $path r]
set content [read $stream]
close $stream
lpd_require [expr {[llength [split [string trim $content] "\n"]] == 25}] "Protected rows lost"
set parents 11
lpd_require [catch {lpb_audit $path $rows -1} msg] "Cached inventory crossed audit pass"
file delete $path
''')


if __name__ == '__main__':
    unittest.main()
