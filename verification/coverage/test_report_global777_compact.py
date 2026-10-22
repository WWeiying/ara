import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import report_global777_compact as m


def el(line, scope='ara_tb.dut.x', checks='12 34'):
    return 'CHECKSUM: "'+checks+'"\nINSTANCE: '+scope+'\n'+line+'\n'


def roots():
    system='ara_tb.dut.i_ara_soc.i_system'
    return [dict(scope=system,name='i_system')]+[
        dict(scope=system+'.g[%d].i_block'%i,name='g[%d].i_block'%i) for i in range(71)]


def csv_blob(stage, rs=None, value='64.11'):
    stream=io.StringIO();writer=csv.writer(stream);writer.writerow(m.SUMMARY_HEADER)
    for i,r in enumerate([dict(scope='ara_tb',name='ara_tb'),*(rs or roots())]):
        writer.writerow([stage,r['scope'],r['scope'],str(i+1),r['name'],r['name'],*([value]*6)])
    return stream.getvalue().encode()


def raw_fixture():
    rows = [dict(Name=name, Depth=str(depth), **{m:'64.11' for m in m.METRICS})
            for depth,name in enumerate(('ara_tb','dut','i_ara_soc','i_system'))]
    rows += [dict(Name=r['name'], Depth='4', **{metric:'64.11' for metric in m.METRICS})
             for r in roots()[1:]]
    rows += [dict(Name='other_%d'%i, Depth='4', **{metric:'64.11' for metric in m.METRICS})
             for i in range(2989-len(rows))]
    return rows


def raw_blob(rows, fields=None):
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields or ['Name','Depth',*m.METRICS])
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode()


class ELTests(unittest.TestCase):
    def setUp(self):
        self.text=el('Toggle x [7:4] "logic x[7:0]"')+el('Branch 12 "TRUE"')
        self.seal=m.semantic_seal(m.semantic(self.text))

    def test_exact_and_range_regrouping(self):
        m.el_gate(self.text.encode(),'applied',self.seal)
        split=el('Toggle 0to1 x [7:4] "logic x[7:0]"\nToggle 1to0 x [7:4] "logic x[7:0]"')+el('Branch 12 "TRUE"')
        m.el_gate(split.encode(),'reloaded',self.seal)

    def test_missing_direction_rejected(self):
        with self.assertRaises(ValueError):m.el_gate(self.text.replace('Toggle x','Toggle 0to1 x').encode(),'applied',self.seal)

    def test_low_bit_rejected(self):
        with self.assertRaises(ValueError):m.el_gate(self.text.replace('[7:4]','[7:3]').encode(),'applied',self.seal)

    def test_whole_vector_rejected(self):
        with self.assertRaises(ValueError):m.el_gate(self.text.replace(' [7:4]','').encode(),'applied',self.seal)

    def test_scope_and_checksum_rejected(self):
        for mutated in (self.text.replace('dut.x','dut.y'),self.text.replace('12 34','12 35')):
            with self.assertRaises(ValueError):m.el_gate(mutated.encode(),'applied',self.seal)

    def test_extra_scope_and_unknown_metric_rejected(self):
        for extra in (el('',scope='ara_tb.dut.new'),el('Condition 4'),el('Toggle control "logic control"')):
            with self.assertRaises(ValueError):m.el_gate((self.text+extra).encode(),'reloaded',self.seal)

    def test_empty_stages_exact_bytes(self):
        for stage in ('raw','reset','final'):
            m.el_gate(b'',stage,self.seal)
            for bad in (b'\n',self.text.encode()):
                with self.assertRaises(ValueError):m.el_gate(bad,stage,self.seal)

    def test_MDA_dimension_identity_not_flattened(self):
        a=el('Toggle arr [2:0][3:0] "logic [3:0][3:0]arr"')
        b=el('Toggle arr [11:0] "logic arr[15:0]"')
        self.assertNotEqual(m.semantic_seal(m.semantic(a)),m.semantic_seal(m.semantic(b)))
        s=m.semantic_seal(m.semantic(a))
        split=''.join(el('Toggle arr [%d][3:0] "logic [3:0][3:0]arr"'%i) for i in range(3))
        m.el_gate(split.encode(),'applied',s)
        with self.assertRaises(ValueError):m.el_gate(a.replace('[2:0]','[3:0]').encode(),'applied',s)

    def test_array_index_not_scalar_alias(self):
        self.assertNotEqual(m.semantic_seal(m.semantic(el('Toggle x[0] "logic x[0]"'))),
                            m.semantic_seal(m.semantic(el('Toggle x "logic x"'))))

    def test_native_scalar_direction_regrouping(self):
        a=el('Toggle x "logic x"')
        b=el('Toggle 0to1 x "logic x"\nToggle 1to0 x "logic x"')
        self.assertEqual(m.semantic_seal(m.semantic(a)),m.semantic_seal(m.semantic(b)))

    def test_ascending_MDA_keeps_actual_indices(self):
        a=el('Toggle p "logic [0:1][3:0]p"')
        b=el('Toggle p [1:0][3:0] "logic [0:1][3:0]p"')
        self.assertEqual(m.semantic_seal(m.semantic(a)),m.semantic_seal(m.semantic(b)))
        with self.assertRaises(ValueError):m.el_gate(b.replace('[1:0]','[2:0]',1).encode(),'applied',m.semantic_seal(m.semantic(a)))

    def test_FSM_context_and_branch_preserved(self):
        a=el('Fsm state_q\nTransition A B')
        with self.assertRaises(ValueError):m.el_gate(a.replace('state_q','other_q').encode(),'applied',m.semantic_seal(m.semantic(a)))
        with self.assertRaises(ValueError):m.semantic(el('Transition A B'))

    def test_actual_777_union_and_CVXIF_low_bits(self):
        text=(m.REFERENCE/'combined.el').read_text()
        self.assertEqual(m.semantic_seal(m.semantic(text)),m.semantic_seal(m.semantic(text)))
        cc=json.loads((m.closure.CAPTURE/'config.json').read_bytes())
        first=(m.closure.CAPTURE/'first.el').read_text()
        self.assertEqual(len(m.cvx.parse_el(first,cc)),18516)
        bad=first.replace('Toggle 1to0 axi_b_payload [1023]', 'Toggle 1to0 axi_b_payload [6]',1)
        self.assertNotEqual(first,bad)
        with self.assertRaises(ValueError):m.cvx.parse_el(bad,cc)


class ConsumerTests(unittest.TestCase):
    def test_supported_roots_no_NA_all_metrics_all_stages(self):
        for stage in m.STAGES:
            for index in (0,1):
                for metric in m.METRICS:
                    rows=list(csv.DictReader(io.StringIO(csv_blob(stage).decode())))
                    rows[index][metric]='NA'
                    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=m.SUMMARY_HEADER)
                    writer.writeheader();writer.writerows(rows)
                    with self.subTest(stage=stage,index=index,metric=metric),self.assertRaises(ValueError):
                        m.summary(stream.getvalue().encode(),stage,roots())

    def test_child_NA_preserved_and_cross_checked(self):
        report=m.summary(csv_blob('raw'),'raw',roots())
        rows=raw_fixture();rows[4]['FSM']='NA'
        report[roots()[1]['scope']]['FSM']='NA'
        m.raw_summary_gate(raw_blob(rows),roots(),report)
        rows[4]['FSM']='64.11'
        with self.assertRaises(ValueError):m.raw_summary_gate(raw_blob(rows),roots(),report)

    def test_full_raw_matches_73_bound_roots_collapsed_names(self):
        m.raw_summary_gate(raw_blob(raw_fixture()),roots(),m.summary(csv_blob('raw'),'raw',roots()))

    def test_every_raw_root_metric_mismatch_rejected(self):
        report=m.summary(csv_blob('raw'),'raw',roots())
        for index in (0,3,4,74):
            for metric in m.METRICS:
                rows=raw_fixture();rows[index][metric]='64.12'
                with self.subTest(index=index,metric=metric),self.assertRaises(ValueError):
                    m.raw_summary_gate(raw_blob(rows),roots(),report)

    def test_raw_supported_roots_no_NA(self):
        report=m.summary(csv_blob('raw'),'raw',roots())
        for index in (0,3):
            for metric in m.METRICS:
                rows=raw_fixture();rows[index][metric]='NA'
                with self.subTest(index=index,metric=metric),self.assertRaises(ValueError):
                    m.raw_summary_gate(raw_blob(rows),roots(),report)

    def test_raw_depth_alias_duplicate_and_rowcount_rejected(self):
        report=m.summary(csv_blob('raw'),'raw',roots())
        variants=[]
        rows=raw_fixture();rows[4]['Depth']='5';variants.append(rows)
        rows=raw_fixture();rows[4]['Name']='i_block';variants.append(rows)
        rows=raw_fixture();rows[5]['Name']=rows[4]['Name'];variants.append(rows)
        variants.append(raw_fixture()[:-1])
        for rows in variants:
            with self.assertRaises(ValueError):m.raw_summary_gate(raw_blob(rows),roots(),report)

    def test_raw_incomplete_duplicate_columns_rejected(self):
        report=m.summary(csv_blob('raw'),'raw',roots())
        rows=raw_fixture();rows[4]['Toggle']=None
        for blob in (raw_blob(rows),raw_blob(raw_fixture(),['Name','Depth',*m.METRICS,'Toggle'])):
            with self.assertRaises(ValueError):m.raw_summary_gate(blob,roots(),report)

    def test_rooted_five_stage_equality(self):
        reports={s:m.summary(csv_blob(s),s,roots()) for s in m.STAGES}
        m.summaries_gate(reports)
        reports['final'][roots()[0]['scope']]['Toggle']='64.12'
        with self.assertRaises(ValueError):m.summaries_gate(reports)

    def test_applied_reload_difference(self):
        reports={s:m.summary(csv_blob(s),s,roots()) for s in m.STAGES}
        reports['applied'][roots()[0]['scope']]['FSM']='81.00'
        with self.assertRaises(ValueError):m.summaries_gate(reports)

    def test_missing_root_field_alias_wrong_stage(self):
        blob=csv_blob('raw')
        for bad in (blob.replace(b'raw',b'applied'),blob.replace(b'"',b'',1).replace(b'64.11',b'101.0',1),
                    blob.replace(b'i_system',b'wrong',1),b'\n'.join(blob.splitlines()[:-1])+b'\n'):
            with self.assertRaises(ValueError):m.summary(bad,'raw',roots())

    def test_wrong_summary_headers(self):
        with self.assertRaises(ValueError):m.summary(csv_blob('raw').replace(b'Condition',b'Other'),'raw',roots())

    def test_selected_exact_order_unique(self):
        with tempfile.TemporaryDirectory() as td:
            a,b=Path(td)/'design.vdb',Path(td)/'case.vdb'
            (b/'snps/coverage/db/testdata/test').mkdir(parents=True)
            selected=[str(b.with_suffix('')/'test')]
            m.membership([str(a),str(b)],selected,1)
            for ledger, actual in [([str(a),str(a)],selected),([str(a),str(b)],['wrong']),([str(a),str(b)],selected*2)]:
                with self.assertRaises(ValueError):m.membership(ledger,actual,1)

    def test_conflicting_pin_and_hash_drift(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.json';p.write_text('{"x":1}')
            sha=hashlib.sha256(p.read_bytes()).hexdigest();r=m.Reader()
            self.assertEqual(r.read(p,sha,True),{'x':1})
            with self.assertRaises(ValueError):r.read(p,'0'*64,True)
            p.write_text('{"x":2}')
            with self.assertRaises(ValueError):m.Reader().read(p,sha,True)
            with self.assertRaises(ValueError):m.merge({str(p):sha},{str(p):'0'*64})

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.json';p.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError):m.Reader().read(p,hashlib.sha256(p.read_bytes()).hexdigest(),True)

    def test_strict_terminal_types_and_cgroup(self):
        c=dict(output='/x',expected_cgroup='/unit',tool_identity=dict(executable='/dve'))
        t=dict(returncode=0,timeout=False,config_seal='sealed',actual_dve=[dict(pid=4,executable_verified=True,cwd='/x',executable='/dve',cgroup='/unit')])
        m.terminal_gate(t,c)
        for key,v in [('returncode',False),('timeout',0),('returncode',1),('timeout',True)]:
            bad=copy.deepcopy(t);bad[key]=v
            with self.assertRaises(ValueError):m.terminal_gate(bad,c)
        for key,v in [('cgroup','/other'),('executable','/wrong'),('cwd','/old'),('executable_verified',False)]:
            bad=copy.deepcopy(t);bad['actual_dve'][0][key]=v
            with self.assertRaises(ValueError):m.terminal_gate(bad,c)

    def test_warnings_and_failed_hooks_rejected(self):
        for bad in ('Warning-[X] text','DVE_COVERAGE_EXPORT_FAILED: text','COMPACT777_FAILED: missing','Error: bad'):
            with self.assertRaises(ValueError):m.diagnostics(bad)
        m.diagnostics('DVE_COVERAGE_EXPORT_DONE\nCOMPACT777_FIVE_PHASE_DONE\n')


class TclIntegration(unittest.TestCase):
    def run_mock(self,reject=False):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td); db=out/'design.vdb';case=out/'case.vdb'
            (db/'snps/coverage/db/design').mkdir(parents=True)
            (db/'snps/coverage/db/design/verilog.design.xml').write_text('design')
            test=case/'snps/coverage/db/testdata/t';test.mkdir(parents=True);(test/'tgl.data.xml').write_text('bits')
            (out/'inputs.txt').write_text(str(db)+'\n'+str(case)+'\n')
            (out/'combined.el').write_text(el('Toggle x [7:4] "logic x[7:0]"'))
            (out/'root-selection.tcl').write_text(m.selection(roots()))
            script='''
set opens 0
set current ara_tb
set selected {}
set active {}
set resets 0
proc gui_open_cov {args} {incr ::opens}
proc gui_get_window_ids {} {return CoverageTable.1}
proc gui_exit {args} {}
proc gui_list_expand {args} {}
proc gui_covtable_show {args} {}
proc gui_cov_show_value {args} {}
proc gui_process_events {args} {}
proc gui_covtable_setroot {args} {set ::current [lindex $args end]}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args end]
}
proc gui_list_get_selected {args} {if {$::selected eq {}} {return {}};return [list $::selected]}
proc gui_list_get_property {args} {
    set col [lindex $args end]
    if {$col<5 || $col>10} {error end}
    return [lindex {Score Line Toggle FSM Condition Branch} [expr {$col-5}]]
}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild]>=0} {
        if {[llength $args]>3} {return {}}
        return 7
    }
    if {[lsearch -exact $args -nextSibling]>=0} {return {}}
    set name ara_tb
    if {[info exists ::p740_root_names($::current)]} {set name $::p740_root_names($::current)}
    if {[lsearch -exact $args -path]>=0} {return $name}
    set i [lsearch -exact $args -text]
    if {$i>=0} {if {[lindex $args [expr {$i+1}]]==0} {return $name};return 64.11}
    error "Unexpected GUI query $args"
}
proc gui_exclusion {args} {if {[lsearch -exact $args -reset]>=0} {set ::active {};incr ::resets}}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -load]>=0} {set f [open $path r];set ::active [read $f];close $f;return}
    set f [open $path w];puts -nonewline $f $::active;close $f
}
proc gui_cov_excl_review {args} {return $::review_ok}
'''
            script+='\nset review_ok '+('0' if reject else '1')+'\n'
            script+='set env(DVE_COVERAGE_OUTPUT) '+m.tcl_atom(out)+'\n'
            script+='set env(DVE_REVIEWED_WAIVERS) '+m.tcl_atom(m.TCL)+'\n'
            script+='source '+m.tcl_atom(m.EXPORT)+'\n'
            script+='puts "OPEN_COUNT $opens RESET_COUNT $resets"\n'
            result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stderr,'')
            self.assertIn('OPEN_COUNT 1',result.stdout)
            if reject:
                self.assertIn('DVE_COVERAGE_EXPORT_FAILED:',result.stdout)
                self.assertNotIn('COMPACT777_FIVE_PHASE_DONE',result.stdout)
                self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')
                return
            self.assertIn('COMPACT777_FIVE_PHASE_DONE',result.stdout)
            self.assertIn('DVE_COVERAGE_EXPORT_DONE',result.stdout)
            for stage in m.STAGES:
                m.summary((out/('modules_'+stage+'.csv')).read_bytes(),stage,roots())
                m.el_gate((out/m.EL_FILES[stage]).read_bytes(),stage,m.semantic_seal(m.semantic((out/'combined.el').read_text())))
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')
            self.assertFalse(any(out.glob('*before*.tsv')))

    def test_real_exporter_csv_and_proc_global_source_five_phases(self):self.run_mock()
    def test_unresolved_import_fails_and_cleanup_recalculates(self):self.run_mock(True)


class RealPrepareCheck(unittest.TestCase):
    def test_actual_frozen777_prepare_then_check_without_self_pin(self):
        # Real CLI and sealed source/native/population evidence; no mocks or EDA.
        # Keep the output (including any failed preparation) for independent review.
        suffix=uuid.uuid4().hex
        out=m.OUT/('global777-compact-host-prepare-check-agent-'+suffix)
        unit='ara-global777-compact-host-test-'+suffix+'.service'
        command=[sys.executable,'-B',str(Path(m.__file__).resolve())]
        result=subprocess.run([*command,'prepare','--output',str(out),'--service-unit',unit],
                              text=True,capture_output=True,timeout=600)
        self.assertEqual(result.returncode,0,result.stderr)
        receipt=json.loads(result.stdout.splitlines()[-1]);seal=receipt['seal']
        c=json.loads((out/'config.json').read_bytes())
        self.assertNotIn(str(out/'config.json'),c['pins'])
        self.assertEqual(c['population'],777)
        checked=subprocess.run([*command,'check','--output',str(out),'--seal',seal],
                               text=True,capture_output=True,timeout=600)
        self.assertEqual(checked.returncode,0,checked.stderr)
        self.assertIn('COMPACT777_CHECK_PASS_NO_EDA',checked.stdout)
        self.assertEqual(m.life.digest(out/'config.json'),seal)
        self.assertFalse((out/'execution.json').exists())
        self.assertFalse((out/'qualification.json').exists())
        print('REAL_PREPARE_CHECK_NO_EDA '+json.dumps(receipt),flush=True)


if __name__=='__main__':unittest.main()
