import subprocess
import unittest
from pathlib import Path

ENTRY = Path(__file__).with_name('export_operand_branch_readonly780.tcl').resolve()

STUB = r'''
set obr_library_only 1
source {%s}
proc gui_list_action {args} {return}
proc gui_covdetail_query {args} {return Branch}
proc gui_list_expand {args} {return}
proc gui_process_events {args} {return}
proc gui_list_get_property {args} {
    set i [lindex $args end]
    if {$i >= 3} {error "End columns"}
    return [lindex {Expression {Native vector} Coverage} $i]
}
proc gui_list_get {args} {
    set op [lindex $args 2]; set item [lindex $args end]
    switch -- $op {
        -firstChild {if {[llength $args] == 3} {return root1}; if {$item eq "root1"} {return leaf1}; return 0}
        -nextSibling {return 0}
        -path {if {$item eq "root1"} {return Item99}; return Item99/vectorA}
        -meta {if {$item eq "root1"} {return NativeParent}; return Branch99.4}
        -text {return [list $item [lindex $args 3]]}
        default {error "Unexpected API $args"}
    }
}
''' % ENTRY


def run(extra):
    result = subprocess.run(['tclsh'], input=STUB + '\n' + extra,
        text=True, capture_output=True, timeout=10)
    if result.stderr:
        raise AssertionError(result.stderr)
    return result.stdout


class ReadOnlyTests(unittest.TestCase):
    def test_full_actual_entry_scope_and_columns(self):
        value = run('obr_snapshot {ara.gen_lanes[0].queue} stdout')
        self.assertIn('{ara.gen_lanes[0].queue}', value)
        self.assertIn('{Expression {Native vector} Coverage}', value)
        self.assertIn('Branch99.4', value)
        self.assertIn('scope_complete', value)

    def test_wrong_type_rejected(self):
        self.assertIn('Wrong native detail type', run('''
proc gui_covdetail_query {args} {return Toggle}
puts [catch {obr_snapshot scope stdout} message]; puts $message
'''))

    def test_missing_columns_rejected(self):
        self.assertIn('Native columns unavailable', run('''
proc gui_list_get_property {args} {error "Unavailable"}
puts [catch {obr_snapshot scope stdout} message]; puts $message
'''))

    def test_cycle_rejected(self):
        self.assertIn('Native cycle/count bound', run('''
rename gui_list_get real_get
proc gui_list_get {args} {
    if {[lindex $args 2] eq "-nextSibling"} {return leaf1}
    return [eval [linsert $args 0 real_get]]
}
puts [catch {obr_snapshot scope stdout} message]; puts $message
'''))

    def test_no_coverage_mutation_commands(self):
        text = ENTRY.read_text()
        for command in ('gui_exclude_items', 'gui_exclusion', 'gui_exclusion_file', 'gui_list_select', '{*}'):
            self.assertNotIn(command, text)


if __name__ == '__main__':
    unittest.main()
