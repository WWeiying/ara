"""Execute the real entry/selection in proc/eval context with GUI boundary stubs."""
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import rvh0_exception60_native772_v2 as m

MOCK = r'''
proc gui_covtable_show {args} {}
proc gui_covtable_setroot {args} {}
proc gui_cov_show_value {args} {}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_open_cov {args} {
    foreach name {design sample test python helper scopes} {
        if {![info exists ::re_$name]} {error "Configuration not global: $name"}
    }
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] w]
    puts $f "The design '$::re_design' was loaded successfully."
    close $f
}
proc gui_list_action {args} {
    set scope [lindex $args end]
    if {![info exists ::mock_labels($scope)]} {error "Foreign full scope"}
    set ::mock_scope $scope
    set ::mock_selection {}
}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_get {args} {
    if {[lindex $args 1] eq "CoverageTable.1"} {
        if {[lsearch -exact $args -firstChild] >= 0} {return 1}
        if {[lsearch -exact $args -path] >= 0} {return ara_tb}
        error "Unexpected coverage table operation"
    }
    set count [llength $::mock_labels($::mock_scope)]
    if {[lsearch -exact $args -firstChild] >= 0} {
        if {[llength $args] == 3} {return 1}
        return 0
    }
    set index [lindex $args end]
    if {[lsearch -exact $args -nextSibling] >= 0} {
        if {$index >= $count} {return 0}
        return [expr {$index + 1}]
    }
    if {[lsearch -exact $args -path] >= 0 || [lsearch -exact $args -meta] >= 0 || [lsearch -exact $args -text] >= 0} {
        return [lindex $::mock_labels($::mock_scope) [expr {$index - 1}]]
    }
    error "Unexpected detail operation"
}
proc gui_list_get_selected {args} {
    if {[lsearch -exact $args -count] >= 0} {return [llength $::mock_selection]}
    if {[lsearch -exact $args -first] >= 0} {return [lindex $::mock_selection 0]}
    if {[lsearch -exact $args -flat] >= 0} {return $::mock_selection}
    error "Unexpected selection query"
}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::mock_selection {};return}
    set token [lindex [lindex $args end] 0]
    if {[lsearch -exact $::mock_labels($::mock_scope) $token] < 0} {error "Bad singleton token"}
    set ::mock_selection [list $token]
}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset] >= 0} {array unset ::mock_active;return}
    if {[lsearch -exact $args -recalculate] >= 0} {return}
    if {[lsearch -exact $args -excluded] >= 0} {
        set name [lindex $::mock_selection 0]
        return [expr {[info exists ::mock_active($::mock_scope,$name)] ? 1 : 0}]
    }
    error "Unexpected exclusion operation"
}
proc gui_exclude_items {args} {
    if {[lindex $args end] ne $::mock_annotation} {error "Annotation mismatch"}
    if {[llength $::mock_selection] != 1} {error "Not singleton"}
    set name [lindex $::mock_selection 0]
    set ::mock_active($::mock_scope,$name) 1
}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -save] >= 0} {
        set f [open $path w]
        if {[array size ::mock_active]} {puts -nonewline $f $::mock_native}
        close $f;return
    }
    if {[lsearch -exact $args -load] >= 0} {
        foreach scope $::mock_scopes {
            foreach label $::mock_targets($scope) {set ::mock_active($scope,$label) 1}
        }
        if {$::mock_bad_reload} {
            set scope [lindex $::mock_scopes end]
            set label [lindex $::mock_targets($scope) end]
            unset ::mock_active($scope,$label)
        }
        return
    }
    error "Unexpected exclusion file operation"
}
proc gui_cov_excl_review {args} {return 1}
proc gui_exit {args} {puts MOCK_GUI_EXIT_CALLED}
'''


class ExactNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review, instances = m.proof()
        cls.c = dict(instances=instances, source_review_sha256=m.REVIEW_SHA,
            baseline=772, baseline_manifest_sha256=m.BASE_SHA, timeout_seconds=900,
            automatic_retry=False,population_application=False,design='frozen-design',sample='one-admitted-vdb',
            test='one-admitted-test',python=sys.executable,helper=str(Path(m.__file__).resolve()),
            pins={str(m.REVIEW):m.REVIEW_SHA})

    def directives(self, pairs=True):
        text = m.candidate(self.c)
        if pairs:
            for i in self.c['instances']:
                for b in i['bindings']:
                    if b['role']=='target' and b['width']==1:
                        whole='Toggle %s "logic %s"' % (b['name'],b['label'])
                        bit=' [0]' if b['kind']=='vectornode' else ''
                        pair='\n'.join('Toggle %s %s%s "logic %s"' % (d,b['name'],bit,b['label']) for d in ('0to1','1to0'))
                        # Names may repeat across different scopes: identical scalar type still required.
                        text=text.replace(whole,pair)
        return text

    def execute(self,out,mutation='',broken=False):
        (out/'DVEfiles').mkdir();m.life.save(out/'config.json',self.c)
        plain=m.selection(self.c);(out/'selection.tcl').write_text(json.dumps(plain) if broken else plain)
        setup='set ::env(DVE_COVERAGE_OUTPUT) '+m.atom(out)+'\n'
        setup+='set ::env(RVH0_EXCEPTION60_SEAL) '+m.atom(m.life.digest(out/'config.json'))+'\n'
        setup+='set ::mock_scopes [list '+' '.join(m.atom(i['scope']) for i in self.c['instances'])+']\n'
        setup+='set ::mock_annotation {'+m.ANNOTATION+'}\nset ::mock_native {'+self.directives()+'}\n'
        setup+='set ::mock_selection {};set ::mock_bad_reload 0;array set ::mock_active {}\n'
        for i in self.c['instances']:
            labels=[b['allowed_labels'][-1] for b in i['bindings']]
            targets=[b['allowed_labels'][-1] for b in i['bindings'] if b['role']=='target']
            setup+='set ::mock_labels('+i['scope']+') [list '+' '.join(m.atom(x) for x in labels)+']\n'
            setup+='set ::mock_targets('+i['scope']+') [list '+' '.join(m.atom(x) for x in targets)+']\n'
        body=setup+MOCK+mutation+'\nproc boot {} {set f [open '+m.atom(m.ENTRY)+' r];set text [read $f];close $f;eval $text}\nboot\n'
        return subprocess.run(['tclsh'],input='if {[catch {\n'+body+'\n} why]} {puts stderr "$why\n$::errorInfo";exit 1}\n',
            text=True,capture_output=True,timeout=180)

    def test_source_config_full_partition(self):
        m.static();m.contract(self.c);m.life.check(self.review['pins'])
        self.assertEqual(sum(len(i['bindings']) for i in self.c['instances']),2854)
        self.assertEqual(sum(b['kind']=='arrays' for i in self.c['instances'] for b in i['bindings']),38)

    def test_actual_session_plain_global_source_proc_eval_all5stages(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out=Path(tmp);p=self.execute(out)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn('RVH0_EXCEPTION60_NATIVE_DONE',p.stdout)
            self.assertNotIn('RVH0_EXCEPTION60_FAILED',p.stdout)
            self.assertIn('MOCK_GUI_EXIT_CALLED',p.stdout)
            bound=json.loads((out/'actual-binding.json').read_bytes())
            self.assertEqual(bound['actual_objects'],2854)
            self.assertEqual(bound['protected'],2794)
            for stage in m.STAGES:
                for index in range(5):m.inventory(out,self.c,stage,index)
                m.check_el(out,self.c,stage)
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_actual_json_selection_failure_before_exclusion(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out=Path(tmp);p=self.execute(out,broken=True)
            self.assertIn('RVH0_EXCEPTION60_FAILED',p.stdout)
            self.assertFalse((out/'first.el').exists())
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_actual_missing_array_before_apply(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out=Path(tmp);scope=self.c['instances'][0]['scope']
            index=next(index for index,b in enumerate(self.c['instances'][0]['bindings']) if b['kind']=='arrays')
            p=self.execute(out,'lset ::mock_labels('+scope+') '+str(index)+' foreign_full_array')
            self.assertIn('RVH0_EXCEPTION60_FAILED',p.stdout)
            self.assertFalse((out/'first.el').exists())
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_actual_partial_reload_rejected_cleanup(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out=Path(tmp);p=self.execute(out,'set ::mock_bad_reload 1')
            self.assertIn('Target/protected membership differs',p.stdout)
            self.assertNotIn('RVH0_EXCEPTION60_NATIVE_DONE',p.stdout)
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_typed_whole_scalar_pair_equivalence(self):
        self.assertEqual(m.records(self.directives(),self.c),m.records(self.directives(False),self.c))

    def test_exact_typed_negative_members_direction_type_scope_checksum(self):
        text=self.directives();pair=next(x for x in text.splitlines() if x.startswith('Toggle 0to1 '))
        vec=next(b for b in self.c['instances'][0]['bindings'] if b['role']=='target' and b['width']>1)
        whole='Toggle %s "logic %s"' % (vec['name'],vec['label'])
        scal=next(b for b in self.c['instances'][-1]['bindings'] if b['role']=='target' and b['width']==1)
        changes=[text.replace(pair+'\n','',1),text+pair+'\n',text.replace('"logic ','"wire ',1),
            text.replace(whole,'Toggle 0to1 %s "logic %s"' % (vec['name'],vec['label']),1),
            text.replace(vec['label'],vec['name']+'[1:0]',1),
            text.replace(self.c['instances'][0]['scope'],self.c['instances'][0]['scope']+'.child',1),
            text.replace(self.c['instances'][0]['toggle_checksum'],'1',1),
            text.replace(m.ANNOTATION,'foreign',1),
            text+'Toggle '+scal['name']+' "logic '+scal['label']+'"\n',
            text+'Toggle lsu_exception_o.cause "logic lsu_exception_o.cause[63:0]"\n',
            text+'Toggle lsu_exception_o.tval "logic lsu_exception_o.tval[63:0]"\n',
            text+'Line 1\n',text.replace('logic '+vec['label'],'logic signed '+vec['label'],1)]
        for changed in changes:
            with self.subTest(change=changed[-90:]),self.assertRaises(ValueError):m.records(changed,self.c)

    def test_config_target_port_scope_width_no_expansion(self):
        for key,value in (('scope','foreign'),('toggle_checksum','1')):
            c=copy.deepcopy(self.c);c['instances'][0][key]=value
            with self.assertRaises(ValueError):m.contract(c)
        c=copy.deepcopy(self.c)
        b=next(b for b in c['instances'][0]['bindings'] if b['role']=='target')
        b['attributes']['portnode']='0' if b['attributes']['portnode']!='0' else '3'
        with self.assertRaises(ValueError):m.contract(c)

    def test_protected_array_and_cause_every_stage(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out=Path(tmp);p=self.execute(out);self.assertIn('RVH0_EXCEPTION60_NATIVE_DONE',p.stdout)
            i=self.c['instances'][0]
            guards=[next(b for b in i['bindings'] if b['kind']=='arrays'),next(b for b in i['bindings'] if b['name'].endswith('.cause'))]
            for stage in m.STAGES:
                path=out/('native_%s_0.tsv'%stage);original=path.read_bytes()
                for guard in guards:
                    rows=list(csv.DictReader(original.decode().splitlines(),delimiter='\t'))
                    for row in rows:
                        if row['name'] in guard['allowed_labels']:row['excluded']='1'
                    with path.open('w',newline='') as stream:
                        writer=csv.DictWriter(stream,fieldnames=['handle','path','meta','name','excluded'],delimiter='\t')
                        writer.writeheader();writer.writerows(rows)
                    with self.assertRaises(ValueError):m.inventory(out,self.c,stage,0)
                    path.write_bytes(original)

    def test_plain_selection_globals_and_no_launch_api(self):
        text=m.selection(self.c)
        self.assertFalse(text.startswith('"'));self.assertNotIn('\\n',text)
        for key in ('design','sample','test','python','helper','scopes'):self.assertIn('set ::re_'+key+' ',text)
        self.assertFalse(hasattr(m,'run'))


if __name__=='__main__':unittest.main()
