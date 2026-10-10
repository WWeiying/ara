import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import report_native_full773_branch720 as p


class ConsumerTests(unittest.TestCase):
    def test_actual_sealed_native720_bytes_and_formal773_zeros(self):
        audit = p.life.read_bound(p.branch.AUDIT, p.branch.AUDIT_SHA)
        expected = p.branch.validate_subset(audit, (p.branch.AUDIT.parent / 'candidate720.el').read_bytes())
        self.assertEqual(len(expected), 720)
        manifest = p.life.read_bound(p.MANIFEST, p.MANIFEST_SHA)
        path = p.MANIFEST.parent / 'combined-bits.json'
        bits = p.life.read_bound(path, manifest['output_pins'][str(path)])
        p.fresh_targets(audit, bits)
    def test_remove_only_branch_preserves_other_native(self):
        text = 'CHECKSUM: "1 2"\nINSTANCE: scope\nToggle x "reg x[1:0]"\nBranch b "foo"\n'
        self.assertEqual(p.nonbranch_text(text), 'CHECKSUM: "1 2"\nINSTANCE: scope\nToggle x "reg x[1:0]"\n')
    def test_branch_only_does_not_become_whole_observer(self):
        self.assertEqual(p.nonbranch_text('CHECKSUM: "1 2"\nINSTANCE: scope\nBranch b "foo"\n'), '')
    def test_whole_observer_preserved(self):
        text = 'CHECKSUM: "1"\nINSTANCE: scope\n'
        self.assertEqual(p.nonbranch_text(text), text)
    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValueError): p.branch.native_inventory(b'CHECKSUM: "1"\nINSTANCE: x\nCondition foo\n')
    def test_conflicting_pins_rejected(self):
        with self.assertRaises(ValueError): p.merge({'x': 'a'}, {'x': 'b'})
    def test_fresh_target_hit_rejected(self):
        audit = {'targets': [dict(scope='s', raw_index=0)]}
        bits = {'metrics': {'branch': {'s': dict(width=101, checksum='1417162425', bits=hex(1 << 100))}}}
        with self.assertRaises(ValueError): p.fresh_targets(audit, bits)
        bits['metrics']['branch']['s']['bits'] = '0'
        p.fresh_targets(audit, bits)
    def test_fresh_wrong_checksum_rejected(self):
        with self.assertRaises(ValueError):
            p.fresh_targets({'targets': [dict(scope='s', raw_index=0)]},
                {'metrics': {'branch': {'s': dict(width=101, checksum='x', bits='0')}}})
    def test_selection_globals_and_protection(self):
        c = dict(scopes=['s'], branch_inventory=[dict(scope='s', selector='1,0', target=True),
                                                dict(scope='s', selector='1,1', target=False)])
        text = p.selection('set retained 1\n', c)
        self.assertIn('set ::op1144_keys(s) [list {1,0} {1,1}]', text)
        self.assertIn('set ::op1144_targets(s) [list {1,0}]', text)

    def test_real_tcl_hook_in_proc_six_audits_nested_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = r'''
set ::env(DVE_COVERAGE_OUTPUT) {@OUTPUT@}
rename source real_source
proc source {path} {
    if {[file tail $path] eq "report_native_full771.tcl"} {
        proc combo_audit {stage mode active} {set ::active $active}
        proc p740_summary {stage} {}
        proc p740_root {} {}
    } else {uplevel 1 [list real_source $path]}
}
proc load_inside_proc {} {real_source {@HOOK@}}
load_inside_proc
set ::op1144_scopes [list s]
set ::op1144_keys(s) [list 1,0 1,1]
set ::op1144_targets(s) [list 1,0]
set ::selected {}
set ::active 0
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Branch}
proc gui_list_expand {args} {}
proc gui_list_get {args} {
    set op [lindex $args 2]; set item [lindex $args 3]
    switch -- $op {
        -firstChild {if {$item eq ""} {return p}; if {$item eq "p"} {return a}; return 0}
        -nextSibling {if {$item eq "a"} {return b}; return 0}
        -path {if {$item eq "p"} {return Item1}; if {$item eq "a"} {return Item1.Branch1.0}; return Item1.MISSING_ELSE1.1}
        -meta {if {$item eq "a"} {return Branch1.0}; return MISSING_ELSE1.1}
        -childCount {return 0}
    }
    error "Unknown query $args"
}
proc gui_list_get_selected {args} {return [list $::selected]}
proc gui_list_select {args} {
    set action [lindex $args 4]; set tokens [lindex $args 5]
    if {$action eq "-unselect"} {set ::selected {}} else {set ::selected $tokens}
}
proc gui_exclusion {args} {return [expr {$::active && $::selected eq "Branch1.0"}]}
foreach {stage mode active} {initial before 0 applied selected 1 reset reset 0 reloaded reloaded 1 final final 0} {
    combo_audit $stage $mode $active
    p740_summary $stage
}
puts OK
'''.replace('@OUTPUT@', str(root)).replace('@HOOK@', str(p.TCL))
            result = subprocess.run(['tclsh'], input=body, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertIn('OK', result.stdout)
            for stage in ('initial', 'applied', 'after_root', 'reset', 'reloaded', 'final'):
                rows = (root / ('states_' + stage + '.tsv')).read_text().splitlines()
                self.assertEqual(len(rows), 3)
                self.assertTrue(rows[2].endswith('\t0'))
                self.assertTrue(rows[1].endswith('\t' + ('1' if stage in ('applied', 'after_root', 'reloaded') else '0')))


if __name__ == '__main__': unittest.main()
