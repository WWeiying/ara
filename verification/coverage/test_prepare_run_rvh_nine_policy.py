import copy
import csv
import inspect
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import prepare_rvh_nine_policy as p
import run_rvh_nine_policy as r


class WiringTests(unittest.TestCase):
    def test_explicit_population_no_relabel(self):
        p.population_gate(727,{'population':727})
        p.population_gate(728,{'population':728})
        for n,stored in ((728,727),(727,728),(True,True),('727',727),(726,726)):
            with self.subTest(n=n,stored=stored),self.assertRaises(ValueError):
                p.population_gate(n,{'population':stored})

    def test_roots_depth_collapsed_generate_and_protected_scope(self):
        rows=[dict(Name='ara_tb',Depth='0',GUIPath='ara_tb'),
            dict(Name='i_ara',Depth='1',GUIPath='ara_tb.i_ara'),
            dict(Name='gen_lanes[0].i_lane',Depth='2',GUIPath='ara_tb.i_ara.gen_lanes[0].i_lane'),
            dict(Name='i_ariane',Depth='1',GUIPath='ara_tb.i_ariane'),
            dict(Name='dtlb',Depth='2',GUIPath='ara_tb.i_ariane.dtlb')]
        cfg={'root_refresh_scopes':['ara_tb.i_ara.gen_lanes[0].i_lane']}
        c={'native_rows':[['ara_tb.i_ariane.dtlb','0,0','Branch0.0','Item0.Branch0.0',False]]}
        roots,names,text=p.root_data(rows,cfg,c)
        self.assertIn('ara_tb.i_ariane.dtlb',roots)
        self.assertNotIn('ara_tb.i_ara.gen_lanes[0]',roots)
        self.assertEqual(names['ara_tb.i_ara.gen_lanes[0].i_lane'],'gen_lanes[0].i_lane')
        self.assertIn('combo_root_names',text)
        for malformed in (rows[:2]+[dict(rows[2],Depth='3')]+rows[3:],
                          rows[:2]+[dict(rows[2],GUIPath='wrong')]+rows[3:],
                          rows+[rows[-1]],rows[:-1]):
            with self.assertRaises(ValueError):p.root_data(malformed,cfg,c)

    def test_pin_conflict_rejected(self):
        self.assertEqual(p.merge_pins({'a':'x'},{'a':'x','b':'y'}),{'a':'x','b':'y'})
        with self.assertRaises(ValueError):p.merge_pins({'a':'x'},{'a':'y'})

    def test_running_failed_reference_rejected_before_verifier(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)
            for status in ('RUNNING','FAILED','PREPARED_NO_DVE'):
                (out/'status.json').write_text(json.dumps({'status':status}))
                with patch.object(p.eight,'verify') as verify,self.assertRaises(ValueError):
                    p.completed_reference(out,'a','b')
                verify.assert_not_called()

    def test_terminal_reference_exact_saved_fields_and_facade_extras(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)
            (out/'status.json').write_text(json.dumps({'status':'HISTORICAL_EIGHT_POLICY_REPORT_NOT_FINAL_APPROVAL'}))
            for name in ('config.json','selection.tcl'):(out/name).write_text('frozen')
            actual=dict(status='HISTORICAL_EIGHT_POLICY_REPORT_NOT_FINAL_APPROVAL',final_reset=True,
                        files={'old':'hash'})
            saved=copy.deepcopy(actual);saved.update(config_sha256='cfg')
            saved['files'].update({str(out/n):p.frozen.sha(out/n) for n in ('config.json','selection.tcl')})
            runtime={'pins':{},'population':727}
            with patch.object(p.frozen,'load_sealed',side_effect=[saved,runtime]),\
                 patch.object(p.eight,'verify',return_value=actual):
                ref,pins=p.completed_reference(out,'cfg','result')
                self.assertEqual(ref,runtime);self.assertIn(str(out/'capture-result.json'),pins)
            saved['files']['extra']='unexpected'
            with patch.object(p.frozen,'load_sealed',return_value=saved),\
                 patch.object(p.eight,'verify',return_value=actual),self.assertRaises(ValueError):
                p.completed_reference(out,'cfg','result')

    def test_no_eda_from_prepare_reader(self):
        for function in (p.prepare,p.read_config,p.completed_reference,r.prepare_entry):
            code=inspect.getsource(function)
            self.assertNotIn('Popen(',code);self.assertNotIn('invoke_run(',code)
        self.assertIs(p.six,p.eight.six)

    def test_foreground_lifecycle_private_binding(self):
        self.assertIn("open('x')",inspect.getsource(r.claim_once))
        self.assertIs(r.invoke_run.__globals__['generic'],p)
        self.assertIn('generic.verify',inspect.getsource(r.invoke_run))
        self.assertIn('generic.six.private',inspect.getsource(r.invoke_run))
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'status.json').write_text('{"status":"FAILED"}')
            with self.assertRaises(ValueError):r.unstarted(out)

    def test_launch_entry_identity_and_drift(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'status.json').write_text('{"status":"PREPARED_NO_DVE"}')
            dep=out/'dep';dep.write_text('immutable')
            cfg=dict(population=728,admission_manifest_sha256='admit728',command=['real-dve'],
                     pins={str(dep):p.frozen.sha(dep)})
            with patch.object(r,'output_path',side_effect=lambda x:x),\
                 patch.object(r,'entry_dependencies',return_value=(dep,)),\
                 patch.object(p,'read_config',return_value=(Mock(),cfg)):
                plan=r.prepare_entry(out,'config')
                self.assertEqual((plan['targets'],plan['protected'],plan['audited']),p.COUNTS)
                seal=p.frozen.sha(out/r.PLAN)
                self.assertEqual(r.reviewed_entry(out,seal)[2],cfg)
                with self.assertRaises(ValueError):r.prepare_entry(out,'config')
                for key,value in (('population',727),('admission_manifest_sha256','wrong'),
                                  ('command',['other']),('targets',5892),('automatic_retry',True)):
                    changed=dict(plan,**{key:value});(out/r.PLAN).write_text(json.dumps(changed))
                    with self.assertRaises(ValueError):r.reviewed_entry(out,p.frozen.sha(out/r.PLAN))
                (out/r.PLAN).write_text(json.dumps(plan));dep.write_text('drift')
                with self.assertRaises(ValueError):r.reviewed_entry(out,p.frozen.sha(out/r.PLAN))

    def test_single_claim_without_process_launch(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'status.json').write_text('{"status":"PREPARED_NO_DVE"}')
            plan={'config_sha256':'cfg'};context=Mock();cfg={}
            with patch.object(r,'reviewed_entry',return_value=(plan,context,cfg)),\
                 patch.object(r,'invoke_run') as invoke:
                r.run_reviewed(out,'launch')
                invoke.assert_called_once_with(out,plan,context,cfg)
                with self.assertRaises(ValueError):r.run_reviewed(out,'launch')

    def test_required_completion_review_evidence(self):
        plan=dict(eight_output='/base',eight_seal='base',completed_eight_output='/done',
            completed_eight_seal='done',completed_eight_result_seal='result',
            rvh_review='/review',rvh_review_seal='review',population=728)
        values=[{'pins':{'base-pin':'a'}},{'pins':{'old-pin':'b'},'population':727},
            {'status':'HISTORICAL_EIGHT_POLICY_REPORT_NOT_FINAL_APPROVAL',
             'config_sha256':'done','final_reset':True,'files':{'output-pin':'c'}},
            {'input_pins':{'rvh-proof':'d'}},{'output_pins':{'rvh-el':'e'}}]
        with patch.object(p.frozen,'load_sealed',side_effect=values):pins=p.evidence_pins(plan)
        self.assertTrue({'base-pin','old-pin','output-pin','rvh-proof','rvh-el'}<=pins.keys())
        values[2]['final_reset']=False
        with patch.object(p.frozen,'load_sealed',side_effect=values),self.assertRaises(ValueError):
            p.evidence_pins(plan)

    def test_real_csv_dependency_eight_snapshot_six_stages(self):
        # Real frozen eight procedure + real batch audit + real CSV writer.
        # Only native point/selection/query and hierarchy restoration are mocked.
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'snapshot').mkdir()
            literal=p.eight.prior.lifecycle.literal
            script=(p.backend.eight_library()+'\nsource '+literal(str(p.SCRIPT.with_name('capture_lzc_batch.tcl'))) + '\n'+
                'set env(DVE_COVERAGE_OUTPUT) '+literal(str(out))+'\n'+r'''
proc qbsapp_root {} {}
proc lzc_batch_point {id group} {}
proc lzc_batch_select {names} {set ::selected [lindex $names 0]}
proc gui_exclusion {args} {return [expr {$::active && $::selected eq "1"}]}
set lzc_batch_groups [list [list ara_tb.i_ara {a,"quoted" == 1'b1} {0 1} {1} {0}]]
set active 0
if {![catch {eight_snapshot_audit before 0} err] || $err ne {invalid command name "csv_row"}} {
    error "Missing CSV dependency not reproduced"
}
'''+p.csv_library()+r'''
foreach stage {before selected reset reloaded after-root final} {
    set active [expr {$stage eq "selected" || $stage eq "reloaded" || $stage eq "after-root"}]
    eight_snapshot_audit $stage $active
}
puts CSV_REAL_DEPENDENCY_PASS
''')
            result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stderr,'')
            self.assertIn('CSV_REAL_DEPENDENCY_PASS',result.stdout)
            for stage in p.backend.STAGES:
                with (out/'snapshot'/('states_'+stage+'.csv')).open(newline='') as f:
                    reader=csv.DictReader(f);rows=list(reader)
                    self.assertEqual(reader.fieldnames,p.eight.mask.native.AUDIT_COLUMNS)
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['Expression'],'a,"quoted" == 1\'b1')
                self.assertEqual(rows[0]['RetainedExcluded'],'0')
                self.assertEqual(rows[0]['TargetExcluded'],str(int(stage in ('selected','reloaded','after-root'))))

    def test_csv_library_contains_only_writer_not_exporter_main(self):
        text=p.csv_library()
        self.assertTrue(p.CSV_SOURCE.read_text().startswith(text.rstrip('\n')))
        self.assertIn('proc csv_row',text)
        self.assertNotIn('export_rows',text);self.assertNotIn('gui_',text)
        self.assertIn(p.CSV_SOURCE,p.dependencies());self.assertIn(p.TCL,p.dependencies())

    def test_synthetic_prepare_read_roundtrip_and_missing_proof_pin(self):
        # Small synthetic filesystem only, never a verification/out prepare.
        # Expensive inherited proof/qualification readers are mocked here.
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);base=root/'base';review=root/'review';out=root/'nine'
            base.mkdir();review.mkdir()
            for name in (*p.eight.prior.HELPERS,'six-library.tcl','seven-selection.tcl',
                         'snapshot-selection.tcl','combined-eight.el','config.json'):
                (base/name).write_text('immutable '+name)
            with (base/'summary_raw.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=['Name','Depth','GUIPath'])
                writer.writeheader();writer.writerows([
                    dict(Name='ara_tb',Depth='0',GUIPath='ara_tb'),
                    dict(Name='i_ara',Depth='1',GUIPath='ara_tb.i_ara'),
                    dict(Name='i_ariane',Depth='1',GUIPath='ara_tb.i_ariane')])
            pins={str(path):p.frozen.sha(path) for path in base.iterdir()}
            runtime=dict(population=727,admission_sha256='admission',pins=pins)
            (base/'runtime-plan.json').write_text(json.dumps(runtime))
            base_seal=p.frozen.sha(base/'runtime-plan.json')
            result=dict(status='HISTORICAL_EIGHT_POLICY_REPORT_NOT_FINAL_APPROVAL',
                        config_sha256=base_seal,final_reset=True,files={})
            (base/'capture-result.json').write_text(json.dumps(result))
            result_seal=p.frozen.sha(base/'capture-result.json')
            proof=review/'proof';proof.write_text('RVH source proof')
            receipt={'input_pins':{str(proof):p.frozen.sha(proof)}}
            (review/'review-receipt.json').write_text(json.dumps(receipt))
            receipt_sha=p.frozen.sha(review/'review-receipt.json')
            (review/'seal.json').write_text(json.dumps({'output_pins':{
                str(review/'review-receipt.json'):receipt_sha}}))
            review_seal=p.frozen.sha(review/'seal.json')
            contract=dict(eight_output=str(base),eight_seal=base_seal,population=727,
                admission_sha256='admission',native_rows=[['ara_tb.i_ariane','0,0',
                    'Branch0.0','Item0.Branch0.0',True]],python={'path':'/usr/bin/python3'})
            cfg=dict(population=727,admission_manifest_sha256='admission',pins=pins,
                     inputs=['design'],root_refresh_scopes=['ara_tb.i_ara'],plan={'tool_identity':{}})
            context=Mock()
            completion_pins=p.merge_pins(pins,{str(base/'runtime-plan.json'):base_seal,
                str(base/'capture-result.json'):result_seal})
            with patch.object(p.frozen,'OUT',root),\
                 patch.object(p.eight,'read_config',return_value=(context,cfg)),\
                 patch.object(p,'completed_reference',return_value=(runtime,completion_pins)),\
                 patch.object(p.backend,'build_contract',return_value=contract),\
                 patch.object(p.backend,'RVH_REVIEW_SHA',receipt_sha),\
                 patch.object(p.backend,'sources',return_value=dict(six=b'six',lzc=b'lzc',snapshot=b'snap',rvh=b'rvh')),\
                 patch.object(p.eight.prior.lifecycle.tool,'launch_command',return_value=['pinned-dve']):
                plan=p.prepare(out,base,base_seal,727,base,base_seal,result_seal,review,review_seal)
                seal=p.frozen.sha(out/p.PLAN)
                actual_context,derived=p.read_config(out,seal)
                self.assertIs(actual_context,context)
                self.assertEqual(derived['rvh9_contract'],contract)
                self.assertEqual(derived['root_refresh_scopes'],['ara_tb','ara_tb.i_ara','ara_tb.i_ariane'])
                self.assertEqual((out/'combined-nine.el').read_bytes(),b'sixlzcsnaprvh')
                self.assertTrue((out/'csv-row-library.tcl').is_file())
                self.assertFalse((out/'DVEfiles').exists())
                changed=copy.deepcopy(plan);del changed['pins'][str(proof)]
                (out/p.PLAN).write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError,'completion/native review pins'):
                    p.read_config(out,p.frozen.sha(out/p.PLAN))


if __name__=='__main__':unittest.main()
