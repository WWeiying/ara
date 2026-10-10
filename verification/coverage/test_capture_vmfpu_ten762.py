import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_vmfpu_ten762 as c


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = c.life.read_bound(c.AUDIT, c.AUDIT_SHA)
        cls.bits = json.loads((c.BASE/'combined-bits.json').read_bytes())
        cls.design = Path((c.BASE/'combined-inputs.txt').read_text().splitlines()[0])
        cls.shape = c.native.read_xml(cls.design/'snps/coverage/db/shape/fsm.verilog.shape.xml')
        cls.gs = c.groups(cls.a, cls.shape, cls.bits)
        cls.plan = dict(groups=cls.gs, targets=10, protected=138)
        cls.records = c.native.expected_records(cls.plan, c.native.Design(cls.design))
        cls.config = dict(expected_records=cls.records)

    def text(self):
        return ''.join('CHECKSUM: "%s %s"\nINSTANCE: %s\nFsm %s "%s"\nANNOTATION: "%s"\n%s %s "%s"\n'%r
                       for r in self.records)

    def test_actual_shape_10_full_complement(self):
        self.assertEqual(sum(len(g['rows']) for g in self.gs), 148)
        self.assertEqual(sum(r['target'] for g in self.gs for r in g['rows']), 10)
        self.assertEqual(sum(r['target'] for g in self.gs if g['mode']=='State' for r in g['rows']), 4)

    def test_all_twenty_reset_arcs_protected(self):
        for p in self.a['points']:
            if p['classification'] == 'REACHABLE_EXTERNAL_RESET_MISSING_PROTECTED':
                r = next(r for g in self.gs if g['scope']==p['scope'] for r in g['rows']
                         if r['raw_index']==p['raw_position'])
                self.assertFalse(r['target'])

    def test_queue_owner_source_and_mutations(self):
        text = c.proof.SOURCE.read_text()
        c.owner_contract(text)
        for mutated in (text.replace('vinsn_queue_d    = vinsn_queue_q;', "vinsn_queue_d = '0;"),
                        text + '\nvinsn_queue_d.issue_cnt -= 1;',
                        text.replace("vinsn_queue_d.issue_cnt == '0 && !prevent_commit", '1')):
            with self.assertRaises(ValueError): c.owner_contract(mutated)

    def test_hit_target_rejected(self):
        b = copy.deepcopy(self.bits)
        scope = self.gs[0]['scope']; m = b['metrics']['fsm'][scope]
        m['bits'] = hex(int(m['bits'],16) | (1 << (36-3)))
        with self.assertRaises(ValueError): c.groups(self.a,self.shape,b)

    def test_checksum_shape_and_reset_candidate_mutations(self):
        b = copy.deepcopy(self.bits); b['metrics']['fsm'][self.gs[0]['scope']]['checksum']='1'
        with self.assertRaises(ValueError): c.groups(self.a,self.shape,b)
        a = copy.deepcopy(self.a)
        next(p for p in a['points'] if p['raw_position']==19)['classification']='UNREACHABLE'
        with self.assertRaises(ValueError): c.groups(a,self.shape,self.bits)

    def test_typed_native_exact_and_order(self):
        c.assert_el(self.text(),self.config)
        self.assertEqual(len(self.records),10)
        self.assertEqual(sum(r[6]=='State' for r in self.records),4)

    def test_state_expanded_el_rejected(self):
        r = list(self.records[0]); r[6:] = ['Transition','LN0_REDUCTION_COMMIT->NO_REDUCTION','4->0']
        extra = 'CHECKSUM: "%s %s"\nINSTANCE: %s\nFsm %s "%s"\nANNOTATION: "%s"\n%s %s "%s"\n'%tuple(r)
        with self.assertRaises(ValueError): c.assert_el(self.text()+extra,self.config)

    def test_duplicate_missing_wrong_type_signature_annotation_rejected(self):
        text=self.text()
        variants=[text+text, '', text.replace('State LN0_REDUCTION_COMMIT "4"','State LN0_REDUCTION_COMMIT "3"'),
                  text.replace(c.native.ANNOTATION,'unapproved'), text.replace('Fsm mfpu_state_q','Fsm other')]
        for v in variants:
            with self.assertRaises(ValueError): c.assert_el(v,self.config)

    def rows(self):
        return [[stage,g['scope'],g['machine']['name'],g['mode'],r['name'],'0',
                 c.expected_query(stage,g['mode'],r['target'])]
                for stage in ('initial','applied','reset','reloaded','final')
                for g in self.gs for r in g['rows']]

    def test_full_five_stage_and_display_observation(self):
        rows=self.rows(); self.assertEqual(len(rows),740)
        for r in rows:
            if r[6]=='STATE_DISPLAY_OBSERVATION': r[5]='1'
        c.audit_points(rows,self.plan)

    def test_reset_protection_missing_duplicate_stage_rejected(self):
        rows=self.rows()
        row=next(r for r in rows if r[0]=='applied' and r[4]=='INTRA_LANE_REDUCTION->NO_REDUCTION')
        row[5]='1'
        with self.assertRaises(ValueError): c.audit_points(rows,self.plan)
        for v in (self.rows()[:-1], self.rows()+self.rows()[:1]):
            with self.assertRaises(ValueError): c.audit_points(v,self.plan)

    def session(self, bad=False):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); (out/'live-ready').touch()
            atom=c.prior.runner.atom
            lines=['set fx_groups {}']
            for g in self.gs:
                fields=[g['scope'],str(c.proof.SOURCE),g['machine']['name'],g['mode']]
                lines.append('lappend fx_groups [list '+' '.join(map(atom,fields))+' [list '+
                             ' '.join(atom(r['name']) for r in g['rows'])+'] [list '+
                             ' '.join(atom(r['name']) for r in g['rows'] if r['target'])+']]')
            lines += ['set v10_design design','set v10_sample sample','set v10_selected sample/seed']
            (out/'selection.tcl').write_text('\n'.join(lines)+'\n')
            script=r'''
set ::v10_test_only 1
source @@HOOK@@
rename p740_root old_root
proc p740_root {} {}
set ::scope {}; set ::mode {}; set ::machine {}; set ::picked {}; set ::mpicked {}; set ::excluded {}
set ::opens 0; set ::saves 0; set ::reviews 0
proc option {args key} {return [lindex $args [expr {[lsearch -exact $args $key]+1}]]}
proc gui_open_cov {args} {incr ::opens}
proc gui_get_window_ids {} {return {Main.1 CoverageTable.1}}
proc gui_list_expand {args} {}
proc gui_list_action {args} {set ::scope [lindex $args end]}
proc gui_open_source {args} {}
proc gui_covdetail_select {args} {
    set i [lsearch -exact $args -fsmMode]
    if {$i>=0} {set ::mode [lindex $args [expr {$i+1}]]}
}
proc names {} {
    foreach g $::fx_groups {if {[lindex $g 0] eq $::scope && [lindex $g 3] eq $::mode} {return [lindex $g 4]}}
    return {}
}
proc gui_list_get_selected {args} {
    if {[option $args -list] eq "fsmnames"} {set picked $::mpicked} else {set picked $::picked}
    if {[lsearch -exact $args -count]>=0} {return [llength $picked]}
    if {[lsearch -exact $args -first]>=0} {return [list [list [lindex $picked 0]]]}
    if {[llength $picked]} {return [list $picked]}
    return [list [names]]
}
proc gui_list_select {args} {
    if {[option $args -list] eq "fsmnames"} {set var ::mpicked} else {set var ::picked}
    if {[lsearch -exact $args -unselect]>=0} {set $var {};return}
    set $var [option $args -select]
    if {$var eq "::mpicked"} {set ::machine [lindex [set $var] 0]}
}
proc key {} {return [list $::scope $::mode [lindex $::picked 0]]}
proc gui_exclude_items {args} {lappend ::excluded [key]}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset]>=0} {set ::excluded {};return}
    if {[lsearch -exact $args -recalculate]>=0} {return}
    if {@@BAD@@ && [llength $::excluded] && $::mode eq "Transition" && [lindex $::picked 0] eq "INTRA_LANE_REDUCTION->NO_REDUCTION"} {return 1}
    if {$::mode eq "State" && [llength $::excluded]} {return 1}
    return [expr {[lsearch -exact $::excluded [key]]>=0}]
}
proc gui_exclusion_file {args} {
    set path [lindex [option $args -file] 0]
    if {[lsearch -exact $args -save]>=0} {
        incr ::saves; set f [open $path w]
        if {[llength $::excluded]} {puts $f $::excluded}
        close $f
    } else {
        set f [open $path r];set ::excluded [string trim [read $f]];close $f
    }
}
proc gui_cov_excl_review {args} {incr ::reviews;return 1}
set env(DVE_COVERAGE_OUTPUT) @@OUT@@
if {[catch {v10_session} message]} {puts stderr $message;exit 2}
if {$::opens!=1 || $::saves!=5 || $::reviews!=1 || [llength $::excluded]} {error "Lifecycle differs"}
puts OK
'''.replace('@@HOOK@@',atom(c.TCL)).replace('@@OUT@@',atom(out)).replace('@@BAD@@','1' if bad else '0')
            result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=25)
            self.assertEqual(result.returncode,2 if bad else 0,result.stdout+result.stderr)
            if bad: self.assertIn('Protected/reset point excluded',result.stderr)
            else:
                self.assertIn('OK',result.stdout)
                c.audit_points(list(csv.reader(io.StringIO((out/'exact-audit.tsv').read_text()),delimiter='\t')),self.plan)

    def test_actual_Tcl_full_five_stage_host_session(self): self.session()
    def test_actual_Tcl_state_expansion_reset_arc_rejected(self): self.session(True)


if __name__=='__main__': unittest.main()
