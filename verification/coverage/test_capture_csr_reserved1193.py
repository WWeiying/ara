import copy
import csv
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_csr_reserved1193 as m


class SourceProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a,targets,nodes,writers=m.proof()
        cls.c=dict(scope=cls.a['scope'],targets=targets,nodes=nodes,writers=writers,
                   timeout_seconds=900,population_application=False)

    def test_actual_all_writers_and_compiled_config(self):
        m.contract(self.c)
        self.assertGreater(len(self.c['writers']),100)
        self.assertEqual(sum(len(t['source_bits']) for t in self.c['targets']),1193)

    def test_no_hold_or_writable_bits(self):
        bits=m.expected_bits()
        self.assertNotIn('mstatus_q.wpri4',bits)
        self.assertNotIn('mscratch_q',bits)
        self.assertNotIn(11,bits['mip_q'])
        self.assertEqual(bits['mstatus_q.uxl'],{0})

    def test_added_writer_rejected(self):
        p=next(p for p in self.a['input_pins'] if p.endswith('/csr_regfile.sv'))
        with self.assertRaisesRegex(ValueError,'writer/mask/config'):
            m.source_check({p:Path(p).read_text()+"\nassign mstatus_d.ube = 1'b1;\n"},self.a['input_pins'])

    def test_changed_mask_rejected(self):
        p=next(p for p in self.a['input_pins'] if p.endswith('/csr_regfile.sv'))
        s=Path(p).read_text();self.assertIn('mstatus_d.wpri3',s)
        with self.assertRaises(ValueError):m.source_check({p:s.replace('mstatus_d.wpri3','mstatus_d.wpri4')},self.a['input_pins'])

    def test_enabled_feature_rejected(self):
        p=self.a['compiled_configuration_file']['path'];s=Path(p).read_text()
        with self.assertRaises(ValueError):m.source_check({p:s+'\nlocalparam RVH_OVERRIDE = 1;\n'},self.a['input_pins'])

    def test_clic_semantic_guard_removed_rejected(self):
        p=next(p for p in self.a['input_pins'] if p.endswith('/csr_regfile.sv'));text=Path(p).read_text()
        evidence=m.semantic_evidence(text)
        self.assertEqual(len(evidence['all_CLIC_modification_guards']),8)
        self.assertEqual(evidence['MIP_all_retained_bits'],[1,3,5,7,9,11])
        with self.assertRaisesRegex(ValueError,'CLIC guard'):
            m.semantic_evidence(text.replace('if (CVA6Cfg.RVSCLIC && clic_mode_o && mcause_q[CVA6Cfg.XLEN-1])','if (1)'))

    def test_new_unconditional_clic_writer_rejected(self):
        p=next(p for p in self.a['input_pins'] if p.endswith('/csr_regfile.sv'))
        with self.assertRaisesRegex(ValueError,'Complete CLIC'):
            m.semantic_evidence(Path(p).read_text()+"\nassign mintstatus_d.uil = 8'd1;\n")

    def test_exact_partial_candidate(self):
        text=m.candidate(self.c);self.assertEqual(len(m.records(text,self.c)),2386)
        self.assertIn('Toggle dcache_q [1] "logic dcache_q[63:0]"',text)

    def test_non_target_bit_rejected(self):
        text=m.candidate(self.c).replace('Toggle dcache_q [1]','Toggle dcache_q [0]')
        with self.assertRaises(ValueError):m.records(text,self.c)

    def test_duplicate_or_missing_direction(self):
        text=m.candidate(self.c)
        with self.assertRaises(ValueError):m.records(text+'Toggle dcache_q [1] "logic dcache_q[63:0]"\n',self.c)
        with self.assertRaises(ValueError):m.records(text.replace('Toggle dcache_q [1]','Toggle 0to1 dcache_q [1]'),self.c)

    def test_wrong_declaration_checksum(self):
        for old,new in [('1176918775','1176918776'),('logic dcache_q[63:0]','logic dcache_q[62:0]')]:
            with self.assertRaises(ValueError):m.records(m.candidate(self.c).replace(old,new),self.c)

    def test_full_inventory_non_target_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            rows=[[m.declaration(n)]*3+['0'] for n in self.c['nodes']]
            bits=[]
            byname={n['name']:n for n in self.c['nodes']}
            for t in self.c['targets']:
                for b in sorted(t['source_bits']+t['retained_source_bits']):
                    name=t['signal'] if byname[t['signal']]['kind']=='node' else t['signal']+'[%d]'%b
                    bits.append([t['signal'],str(b),name,name,name,'0','0'])
            def write():
                for path,header,data in [('objects-before.tsv',['path','meta','name','excluded'],rows),
                    ('bits-before.tsv',['signal','bit','path','meta','name','0to1','1to0'],bits)]:
                    with (out/path).open('w',newline='') as f:
                        w=csv.writer(f,delimiter='\t');w.writerow(header);w.writerows(data)
            write();self.assertGreater(m.check_inventory(out,self.c,'before'),1193)
            bits[0][-1]='1';write()
            with self.assertRaises(ValueError):m.check_inventory(out,self.c,'before')

    def test_retained_bit_exclusion_rejected(self):
        self.assertEqual(next(t for t in self.c['targets'] if t['signal']=='dcache_q')['retained_source_bits'],[0])
        c=copy.deepcopy(self.c);c['targets'][0]['source_bits'].append(0)
        with self.assertRaises(ValueError):m.contract(c)

    def test_actual_2077_native_inventory_exact_alias_bijection(self):
        path=m.life.OUT/'csr-pmp0-internal770-native765-agent-20261007-01/native_before_0.tsv'
        with path.open() as f:rows=list(csv.reader(f,delimiter='\t'))[1:]
        aliases={alias:n['name'] for n in self.c['nodes'] for alias in m.base.aliases(n)}
        self.assertEqual(len(rows),2077)
        self.assertEqual({aliases[r[3]] for r in rows},{n['name'] for n in self.c['nodes']})
        self.assertTrue(all(r[1]==r[2]==r[3] for r in rows))


class TclEntry(unittest.TestCase):
    def test_source_from_proc_global_selection_and_exact_bit_direction(self):
        script='set ::csr_test_only 1\nsource {'+str(m.HOOK)+'}\n'
        script+='''
set ::csr_targets [list [list dcache_q {dcache_q[63:0]} vectornode]]
set ::csr_scope scope
set ::selected {}
proc gui_list_get_selected {args} {
    if {[lsearch $args -count]>=0} {return [llength $::selected]}
    return $::selected
}
proc gui_list_select {args} {
    if {[lsearch $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args end]
}
proc exercise {} {csr_select {dcache_q[0]}}
exercise
if {$::selected ne {{dcache_q[0]}}} {error "Wrong data quoting"}
puts EXACT_GLOBAL_ENTRY_PASS
'''
        r=subprocess.run(['tclsh'],input='if {[catch {\n'+script+'\n} msg]} {puts stderr $msg;exit 1}\n',text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('EXACT_GLOBAL_ENTRY_PASS',r.stdout)

    def test_full_standalone_five_stage_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            (path/'selection.tcl').write_text('''set ::fma_design design
set ::fma_vdb vdb
set ::fma_test test
set ::csr_scope scope
set ::csr_targets [list [list dcache_q {dcache_q[1:0]} vectornode]]
set ::csr_python python
set ::csr_helper helper
''')
            (path/'candidate.el').write_text('Toggle dcache_q [1] "logic dcache_q[1:0]"\n')
            script='set ::csr_test_only 1\nsource {'+str(m.HOOK)+'}\nset ::env(DVE_COVERAGE_OUTPUT) {'+tmp+'}\n'
            script+='''
set ::active 0;set ::expanded 0;set ::selected {}
proc help {args} {}
proc gui_open_cov {args} {}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_action {args} {set ::expanded 0}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_list_get_selected {args} {
    if {[lsearch $args -count]>=0} {return [llength $::selected]}
    return $::selected
}
proc gui_list_select {args} {
    if {[lsearch $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args end]
}
proc gui_list_get {args} {
    set flag [lindex $args 2];set item [lindex $args end]
    if {$flag eq "-firstChild"} {
        if {[llength $args]==3} {return 1};return 0
    }
    if {$flag eq "-nextSibling"} {
        if {$::expanded && $item eq "1"} {return 2};return 0
    }
    if {$::expanded} {return "dcache_q\\[[expr {$item-1}]\\]"}
    return {dcache_q[1:0]}
}
proc gui_cov_tgl_double_click {args} {
    if {$args ne {-id CovDetail.1 -item {dcache_q[1:0]}}} {error "Wrong exact command"}
    set ::expanded 1
}
proc gui_exclusion {args} {
    if {[lsearch $args -reset]>=0} {set ::active 0;return}
    if {[lsearch $args -recalculate]>=0} {return}
    return [expr {$::active && [lindex $::selected 0] ne {dcache_q[0]}}]
}
proc gui_exclusion_file {args} {
    set name [file tail [lindex [lindex $args end] 0]]
    if {[lsearch $args -load]>=0} {set ::active 1;return}
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) $name] w]
    if {$::active} {puts $f {Toggle dcache_q [1] "logic dcache_q[1:0]"}}
    close $f
}
rename exec real_exec
proc exec {args} {return MOCK_HOST_GATE}
csr_session
if {$::active} {error "Final reset missing"}
puts FULL_ENTRY_PASS
'''
            r=subprocess.run(['tclsh'],input='if {[catch {\n'+script+'\n} msg]} {puts stderr $msg;puts stderr $::errorInfo;exit 1}\n',
                             text=True,capture_output=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            for stage in m.STAGES:
                with (path/('bits-'+stage+'.tsv')).open() as f:rows=list(csv.reader(f,delimiter='\t'))
                self.assertEqual([r[1] for r in rows[1:]],['0','1'])
                self.assertEqual(rows[1][-2:],['0','0'])
                value='1' if stage in ('selected','reloaded') else '0'
                self.assertEqual(rows[2][-2:],[value,value])
            for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
                self.assertEqual((path/name).read_bytes(),b'')


if __name__=='__main__':unittest.main()
