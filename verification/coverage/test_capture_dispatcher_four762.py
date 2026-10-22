import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_dispatcher_four762 as c


class FourTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(c.AUDIT.read_bytes())
        cls.bits = json.loads((c.BASE/'combined-bits.json').read_bytes())
        cls.design = Path((c.BASE/'combined-inputs.txt').read_text().splitlines()[0])
        cls.shape = c.native.read_xml(cls.design/'snps/coverage/db/shape/fsm.verilog.shape.xml')
        cls.gs = c.groups(cls.shape, cls.bits, cls.audit['scope'])
        cls.plan = dict(groups=cls.gs, targets=4, protected=88,
                        strategy='direct-transition-only-66', point_query_authority='saved-native-identity')
        cls.records = c.native.expected_records(cls.plan, c.native.Design(cls.design))

    def test_actual_shape_exact4_full_complement(self):
        self.assertEqual([r['raw_index'] for g in self.gs for r in g['rows'] if r['target']], [31,32,34,37])
        self.assertEqual(sum(len(g['rows']) for g in self.gs), 92)
        self.assertFalse(any(r['target'] for g in self.gs if g['mode']=='State' for r in g['rows']))
        self.assertEqual(len(self.records), 4)

    def test_remaining13_and_prior11_protected(self):
        targets = c.TARGETS
        self.assertEqual(len([r for r in self.audit['remaining'] if r['raw_position'] not in targets]),13)
        by_raw = {r['raw_index']:r for g in self.gs for r in g['rows']}
        self.assertTrue(all(not by_raw[r['raw_position']]['target'] for r in self.audit['previously_qualified']))

    def test_hit_rejected(self):
        b = copy.deepcopy(self.bits)
        m = b['metrics']['fsm'][self.audit['scope']]
        m['bits'] = hex(int(m['bits'],16)|(1<<(91-31)))
        with self.assertRaises(ValueError): c.groups(self.shape,b,self.audit['scope'])

    def test_checksum_rejected(self):
        b = copy.deepcopy(self.bits);b['metrics']['fsm'][self.audit['scope']]['checksum']='1'
        with self.assertRaises(ValueError):c.groups(self.shape,b,self.audit['scope'])

    def test_wrong_width_rejected(self):
        b=copy.deepcopy(self.bits);b['metrics']['fsm'][self.audit['scope']]['width']=82
        with self.assertRaises(ValueError):c.groups(self.shape,b,self.audit['scope'])

    def text(self):
        return ''.join('CHECKSUM: "%s %s"\nINSTANCE: %s\nFsm %s "%s"\nANNOTATION: "%s"\n%s %s "%s"\n'%r for r in self.records)

    def test_native_signatures_exact(self):
        self.assertEqual(c.native.native_records(self.text()),self.records)

    def test_extra_state_not_authorized(self):
        text=self.text().replace('Transition OVERLAP_ISSUE_ORIGINAL->OVERLAP_CAPTURE "8->6"',
                                'State OVERLAP_ISSUE_ORIGINAL "8"')
        self.assertNotEqual(c.native.native_records(text),self.records)

    def test_native_duplicate_rejected(self):
        with self.assertRaises(ValueError): c.native.native_records(self.text()+self.text())

    def test_native_wrong_signature_rejected_by_binding(self):
        self.assertNotEqual(c.native.native_records(self.text().replace('"8->6"','"8->7"')),self.records)

    def test_private_launcher_keeps_full_namespace(self):
        original=c.runner.verify
        fake_globals=dict(c.runner.run.__globals__,verify=c.verify,TCL=c.TCL)
        self.assertIs(fake_globals['subprocess'].STDOUT,subprocess.STDOUT)
        self.assertIs(fake_globals['os'],c.runner.os)
        self.assertIs(c.runner.verify,original)

    def tcl_session(self, bad=False):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'live-ready').touch()
            lines=['set fx_groups {}']
            for g in self.gs:
                atom=c.runner.atom
                fields=[g['scope'],str(c.life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'),g['machine']['name'],g['mode']]
                lines.append('lappend fx_groups [list '+' '.join(map(atom,fields))+' [list '+
                    ' '.join(atom(r['name']) for r in g['rows'])+'] [list '+
                    ' '.join(atom(r['name']) for r in g['rows'] if r['target'])+']]')
            lines+=['set d4_design design','set d4_sample sample','set d4_selected sample/seed']
            (out/'selection.tcl').write_text('\n'.join(lines)+'\n')
            script=r'''
set ::d4_test_only 1
source HOOK
if {[info exists ::open_count]} {error "Nested source opened database"}
rename p740_root original_p740_root
proc p740_root {} {}
set ::machine {}; set ::mode {}; set ::picked {}; set ::mpicked {}; set ::excluded {}
set ::open_count 0; set ::save_count 0; set ::review_count 0
proc gui_open_cov {args} {incr ::open_count}
proc gui_get_window_ids {} {return CoverageTable.1}
proc gui_list_expand {args} {}
proc gui_list_action {args} {}
proc gui_open_source {args} {}
proc gui_covdetail_select {args} {
    set i [lsearch -exact $args -fsmMode]
    if {$i>=0} {set ::mode [lindex $args [expr {$i+1}]]}
}
proc option {args key} {return [lindex $args [expr {[lsearch -exact $args $key]+1}]]}
proc names {} {
    foreach g $::fx_groups {if {[lindex $g 2] eq $::machine && [lindex $g 3] eq $::mode} {return [lindex $g 4]}}
    return {}
}
proc gui_list_get_selected {args} {
    set listname [option $args -list]
    if {$listname eq "fsmnames"} {set selected $::mpicked} else {set selected $::picked}
    if {[lsearch -exact $args -count]>=0} {return [llength $selected]}
    if {[lsearch -exact $args -first]>=0} {return [list [list [lindex $selected 0]]]}
    if {[llength $selected]} {return [list $selected]}
    return [list [names]]
}
proc gui_list_select {args} {
    set name [option $args -list]
    if {$name eq "fsmnames"} {set var ::mpicked} else {set var ::picked}
    if {[lsearch -exact $args -unselect]>=0} {set $var {}; return}
    set $var [option $args -select]
    if {$name eq "fsmnames"} {set ::machine [lindex [set $var] 0]}
}
proc key {} {return [list $::machine $::mode [lindex $::picked 0]]}
proc gui_exclude_items {args} {lappend ::excluded [key]}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset]>=0} {set ::excluded {}; return}
    if {[lsearch -exact $args -recalculate]>=0} {return}
    if {@@BAD@@ && [llength $::excluded] && $::mode eq "Transition" && [lindex $::picked 0] eq "NORMAL_OPERATION->OVERLAP_WAIT_ORIGINAL"} {return 1}
    # Actual target display projection may be0. EL is independent authority.
    return 0
}
proc gui_exclusion_file {args} {
    set path [lindex [option $args -file] 0]
    if {[lsearch -exact $args -save]>=0} {
        incr ::save_count;set f [open $path w];if {[llength $::excluded]} {puts $f native};close $f
    } else {set ::excluded {{state_q Transition OVERLAP_ISSUE_ORIGINAL->OVERLAP_CAPTURE}}}
}
proc gui_cov_excl_review {args} {incr ::review_count;return 1}
set env(DVE_COVERAGE_OUTPUT) @@OUT@@
if {[catch {dispatcher_four_session} message]} {puts stderr $message;exit 2}
if {$::open_count!=1 || $::save_count!=5 || $::review_count!=1} {error "Lifecycle differs"}
puts OK
'''.replace('HOOK',c.runner.atom(c.TCL)).replace('@@OUT@@',c.runner.atom(out)).replace('@@BAD@@','1' if bad else '0')
            result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=20)
            if not bad:
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('OK',result.stdout)
                rows=list(csv.reader(io.StringIO((out/'exact-audit.tsv').read_text()),delimiter='\t'))
                c.native.audit_points(rows,self.plan)
                self.assertEqual(len(rows),460)
            else:
                self.assertEqual(result.returncode,2,result.stdout+result.stderr)
                self.assertIn('Protected/reset exclusion mismatch',result.stderr)

    def test_real_nested_tcl_primitives_all_five_stages(self):self.tcl_session()
    def test_real_tcl_protected_transition_rejects(self):self.tcl_session(True)


if __name__=='__main__':unittest.main()
