import copy
import csv
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_tlb_rvh0_726 as m


class ExactProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instances,cls.induction,cls.pins=m.proof()
        cls.c=dict(instances=cls.instances)
        cls.text=m.candidate(cls.c)
        cls.source=(m.life.ROOT/'hardware/deps/cva6/core/cva6_mmu/cva6_tlb.sv').read_text()

    def test_real_source_compiled_identity_and_bounds(self):
        self.assertEqual(len(m.records(self.text,self.c)),8448)
        self.assertEqual(sum(len(i['targets']) for i in self.instances),726)
        self.assertEqual(sum(m.width(n) for i in self.instances for n in i['targets']),4224)
        self.assertTrue(all(n['portnode']=='0' for i in self.instances for n in i['targets']))
        m.source_induction(self.source)

    def test_rvh_guard_and_reset_mutations(self):
        mutations=[self.source.replace('if (CVA6Cfg.RVH) content_n[i].gpte','content_n[i].gpte'),
                   self.source.replace("content_q   <= '{default: 0};",'content_q <= content_n;'),
                   self.source+'\nassign content_n[0].gpte.ppn = update_i.content.ppn;\n',
                   self.source+'\nassign g_content.ppn = update_i.content.ppn;\n']
        for text in mutations:
            with self.assertRaises(ValueError):m.source_induction(text)

    def test_prior_scope_ancestor_and_broad_duplicates(self):
        m.no_overlap('INSTANCE: other.module\n')
        for text in ('INSTANCE: '+m.SCOPES[0], 'INSTANCE: '+m.PREFIX.rstrip('.'), 'MODULE: cva6_tlb'):
            with self.assertRaises(ValueError):m.no_overlap(text)

    def test_missing_direction_and_duplicate(self):
        line=next(l for l in self.text.splitlines() if l.startswith('Toggle '))
        for text in (self.text.replace(line,line.replace('Toggle ','Toggle 0to1 '),1),
                     self.text+'\n'+line+'\n'):
            with self.assertRaises(ValueError):m.records(text,self.c)

    def test_foreign_field_checksum_declaration_and_extra_scope(self):
        field=self.instances[0]['targets'][0]
        for text in (self.text.replace('817233724','817233725'),
                     self.text+'Toggle clk_i "logic clk_i"\n',
                     self.text+'INSTANCE: foreign\n',
                     self.text+'CHECKSUM: "'+m.CHECKSUM+'"\n',
                     self.text.replace('"logic '+m.declaration(field)+'"','"logic foreign"',1)):
            with self.assertRaises(ValueError):m.records(text,self.c)

    def test_order_only_equal(self):
        blocks=self.text.split('CHECKSUM: ')[1:]
        reversed_blocks=''.join('CHECKSUM: '+b for b in reversed(blocks))
        self.assertEqual(m.records(self.text,self.c),m.records(reversed_blocks,self.c))

    def test_complete_typed_complement_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);i=self.instances[0];target={n['name'] for n in i['targets']}
            rows=[['path','meta','name','excluded']]
            for n in i['nodes']:
                alias=sorted(m.csr.original.base.aliases(n))[0]
                rows.append([alias,alias,alias,'1' if n['name'] in target else '0'])
            p=out/'objects-selected-0.tsv'
            def write():
                with p.open('w',newline='') as f:csv.writer(f,delimiter='\t').writerows(rows)
            write();self.assertEqual(len(m.inventory(out,self.c,'selected',0)),len(i['nodes']))
            protected=next(r for r in rows[1:] if r[2]=='clk_i');protected[3]='1';write()
            with self.assertRaisesRegex(ValueError,'Protected'):m.inventory(out,self.c,'selected',0)
            protected[3]='0';rows.pop();write()
            with self.assertRaises(ValueError):m.inventory(out,self.c,'selected',0)


class RealPercent(unittest.TestCase):
    def test_actual_csr_percent_fixture(self):
        c=m.life.read_bound(m.pct.SOURCE/'config.json',m.pct.CONFIG_SHA)
        value=m.pct.metrics(m.pct.SOURCE,c,'before')
        self.assertEqual(value['Toggle'],'1.71%')
        for bad in ('1.71%%','NaN%',' 1.71%','101%','1.71'):
            with self.assertRaises(ValueError):m.pct.percent(bad)

    def test_actual_rooted_schema_and_reset(self):
        text=(m.pct.SOURCE/'rooted_before.csv').read_text()
        header=text.splitlines()[0]
        source=text.splitlines()[1]
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            rows=[]
            for scope in m.SCOPES:
                rows.append(source.replace('ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i',scope)
                    .replace('"csr_regfile_i"','"'+scope.rsplit('.',1)[1]+'"'))
            (out/'rooted_before.csv').write_text(header+'\n'+'\n'.join(rows)+'\n')
            result=m.metrics(out,'before');self.assertEqual(set(result),set(m.SCOPES))
            values={s:copy.deepcopy(result[m.SCOPES[0]]) for s in m.STAGES}
            values['selected']['Toggle']=values['reloaded']['Toggle']='2.00%'
            m.pct.compare_metrics(values)
            values['final']['Toggle']='1.72%'
            with self.assertRaises(ValueError):m.pct.compare_metrics(values)


class StandaloneTcl(unittest.TestCase):
    def test_full_entry_namespace_five_stages_stdout_paths_and_idle_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            selection='set ::fma_design design\nset ::fma_vdb vdb\nset ::fma_test test\nset ::csr_python python\nset ::tlb_helper helper\n'
            selection+='set ::tlb_scopes [list {'+m.SCOPES[0]+'} {'+m.SCOPES[1]+'}]\nset ::p740_scopes $::tlb_scopes\n'
            for s in m.SCOPES:selection+='set ::p740_root_names('+s+') '+s.rsplit('.',1)[1]+'\n'
            (out/'selection.tcl').write_text(selection);(out/'candidate.el').write_text('exact\n')
            script='set ::env(DVE_COVERAGE_OUTPUT) {'+tmp+'}\n'+'''
set ::active 0;set ::root ara_tb
array set ::selected {CovDetail.1 {} CoverageTable.1 {}}
proc gui_open_cov {args} {}
proc gui_covtable_show {args} {}
proc gui_covtable_setroot {args} {set ::root [lindex $args end]}
proc gui_cov_show_value {args} {}
proc gui_process_events {args} {}
proc gui_list_expand {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_list_get_selected {args} {
 set id [lindex $args 1]
 if {[lsearch $args -count]>=0} {return [llength $::selected($id)]}
 return [list $::selected($id)]
}
proc gui_list_select {args} {
 set id [lindex $args 1]
 if {[lsearch $args -unselect]>=0} {set ::selected($id) {};return}
 set ::selected($id) [lindex $args end]
}
proc gui_list_get_property {args} {return [lindex {Score Line Toggle FSM Condition Branch} [expr {[lindex $args end]-5}]]}
proc gui_list_get {args} {
 set id [lindex $args 1];set flag [lindex $args 2]
 if {$flag eq "-firstChild"} {if {[llength $args]==3} {return 1};return 0}
 if {$flag eq "-nextSibling"} {return 0}
 if {$id eq "CovDetail.1"} {return {content_q[0].gpte.v}}
 if {$flag eq "-text" && [lindex $args 3]>=5} {
  if {[lindex $args 3]==7} {if {$::active} {return 50.00%};return 40.00%}
  return 60.00%
 }
 return [lindex [split $::root .] end]
}
proc gui_exclusion {args} {
 if {[lsearch $args -reset]>=0} {set ::active 0;return}
 if {[lsearch $args -recalculate]>=0} {return}
 return $::active
}
proc gui_exclusion_file {args} {
 set file [lindex [lindex $args end] 0]
 if {[lsearch $args -load]>=0} {set ::active 1;return}
 set f [open $file w];if {$::active} {puts $f exact};close $f
}
rename exec real_exec
proc exec {args} {
 if {[lindex $args 4] ne "--output" || [lindex $args 5] ne $::env(DVE_COVERAGE_OUTPUT)} {error "stdout/output mismatch"}
 return HOST_GATE
}
proc gui_exit {args} {puts REAL_IDLE_EXIT}
'''
            script+='source {'+str(m.HOOK)+'}\nupdate\n'
            result=subprocess.run(['tclsh'],input='if {[catch {\n'+script+'\n} msg]} {puts stderr $msg;puts stderr $::errorInfo;exit 1}\n',text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout.splitlines().count('TLB726_NATIVE_DONE'),1,result.stdout+result.stderr)
            self.assertIn('REAL_IDLE_EXIT',result.stdout)
            self.assertFalse((out/'error.txt').exists(),result.stdout)
            for stage in m.STAGES:self.assertEqual(set(m.metrics(out,stage)),set(m.SCOPES))
            for stage in ('before','reset','final'):self.assertEqual((out/m.EL_FILES[stage]).read_bytes(),b'')
            self.assertEqual((out/'first.el').read_bytes(),(out/'second.el').read_bytes())


if __name__=='__main__':unittest.main()
