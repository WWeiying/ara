#!/usr/bin/env python3
"""Host-only boundaries for one shared ten-job adapter, not a DUT oracle run."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import replay as r
from checker import common,read,sha,HERE

class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cases=r.checker.scope()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def artifact(self,case=None):
        case=case or self.cases[0];root=self.root/'test';root.mkdir();(root/'work').mkdir()
        shutil.copyfile(case['elf'],root/'input.elf')
        ledger=dict(simv='/sealed/simv',files={'simv':'identity'})
        command=dict(command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
            '+PRELOAD='+str(root/'input.elf'),'+TESTCASE='+case['id'],'+NO_FSDB',
            '+COMMIT_TRACE='+str(root/'commit_trace.csv')],cwd=str(root/'work'))
        common.save(root/'command.json',command)
        common.save(root/'inputs.json',dict(binary=dict(source=case['elf'],path=str(root/'input.elf'),sha256=case['sha256']),
            simv=dict(path=ledger['simv'],image_sha256=ledger['files'])))
        common.save(root/'trace_summary.json',dict(status='VALID'))
        (root/'console.log').write_text(case['pass_markers'][0]+'\n'+common.SUCCESS+'\n$finish\n')
        (root/'work/run.vcs.log').write_text('normal\n');(root/'commit_trace.csv').write_text('synthetic schema only\n')
        result=SimpleNamespace(name=case['id'],kind='app',status='PASS',returncode=0,elapsed_s=1.0,reason='',artifact_dir=root)
        return result,case,ledger

    def check(self,result,case,ledger):common.check_artifacts(result,r.checker.runtime_case(case),ledger)

    def test_scope40_not42(self):
        self.assertEqual(len(self.cases),10)
        self.assertEqual(sum(len(c['source_cases']) for c in self.cases),36)
        self.assertEqual(len(set(s for c in self.cases for s in c['source_cases'])|set(r.gates.PILOT_IDS)),40)
        self.assertTrue(set(self.cases[-1]['positive_controls']).isdisjoint(
            s for c in self.cases for s in c['source_cases']))

    def test_last_two_full_contract(self):
        c=self.cases[8]
        self.assertEqual((c['MX_N'],c['checks'],len(c['source_cases'])),(2,1509,2))
        self.assertEqual(c['timeout_s'],3000)

    def test_budgets_and_max3(self):
        self.assertEqual([c['timeout_s'] for c in self.cases],[5700,5400,6000,5700,6000,5700,6300,6000,3000,5400])
        self.assertEqual((r.JOBS,r.WORKER_BOUND,r.OUTER),(3,25200,27000))
        self.assertEqual(sum(c['timeout_s']+600 for c in self.cases)/3+2/3*6900,25000)

    def test_base_runner_does_not_override_per_elf_budget(self):
        opts=r.build_options(SimpleNamespace,self.root,self.root,dict(simv='/sealed/simv'))
        self.assertIsNone(opts.timeout_s)
        tests=r.tests_for(lambda *args:SimpleNamespace(name=args[0],timeout_s=args[-1]),self.cases)
        self.assertEqual([opts.timeout_s or t.timeout_s for t in tests],[c['timeout_s'] for c in self.cases])

    def test_j4_same_old_elf_and_observer(self):
        c=self.cases[-1]
        self.assertEqual(c['sha256'],r.checker.J4_SHA)
        self.assertEqual(c['old_acceptance_image'],'M2_NOT_M6')
        self.assertTrue((r.checker.J4/'csv_check.py').is_file())
        self.assertEqual(c['checks'],4133)

    def test_runtime_mapping_no_mutation(self):
        result,c,ledger=self.artifact();saved=deepcopy(c);self.check(result,c,ledger)
        self.assertEqual(c,saved)
        with self.assertRaises(ValueError):common.check_artifacts(result,c,ledger)

    def test_wrong_seed(self):self.bad_command(3,'+ntb_random_seed=2')
    def test_wrong_preload(self):self.bad_command(4,'+PRELOAD=/wrong.elf')
    def test_wrong_testcase(self):self.bad_command(5,'+TESTCASE=historical_name')
    def bad_command(self,index,value):
        result,c,ledger=self.artifact();cmd=read(result.artifact_dir/'command.json');cmd['command'][index]=value
        common.save(result.artifact_dir/'command.json',cmd)
        with self.assertRaises(ValueError):self.check(result,c,ledger)

    def test_wrong_cwd(self):
        result,c,ledger=self.artifact();cmd=read(result.artifact_dir/'command.json');cmd['cwd']='/wrong'
        common.save(result.artifact_dir/'command.json',cmd)
        with self.assertRaises(ValueError):self.check(result,c,ledger)

    def test_elf_drift(self):
        result,c,ledger=self.artifact();(result.artifact_dir/'input.elf').write_bytes(b'wrong')
        with self.assertRaises(ValueError):self.check(result,c,ledger)

    def test_image_drift(self):
        result,c,ledger=self.artifact();ledger['files']={'simv':'other'}
        with self.assertRaises(ValueError):self.check(result,c,ledger)

    def test_missing_oracle(self):
        result,c,ledger=self.artifact();(result.artifact_dir/'console.log').write_text(common.SUCCESS+'\n$finish')
        with self.assertRaises(ValueError):self.check(result,c,ledger)

    def test_partial_failure_veto(self):
        for line in ('NF2_REMAINING34_SV39_FAIL case1','SEGMENT_SV39_FAIL','BOARD_REPLAY_MISMATCH'):
            self.assertIsNotNone(r.checker.VETO.search(line))

    def durable(self,check,rc=0):
        result,_,_=self.artifact();result.returncode=rc
        if rc:result.status='FAIL'
        class Parent:
            def __init__(self):pass
            def _run_test(self,test,image):return result
        abort=threading.Event()
        got=r.checked_runner(Parent,abort,check,lambda name:None)()._run_test(SimpleNamespace(name=result.name),None)
        return got,read(result.artifact_dir/'child_outcome.unvalidated.json'),abort

    def test_checkerthrow_durable0(self):
        def throws(result):raise ValueError('deliberate postcheck exception')
        got,raw,abort=self.durable(throws)
        self.assertEqual((got.status,got.returncode,raw['status'],raw['returncode']),('FAIL',0,'PASS',0))
        self.assertTrue(abort.is_set());self.assertFalse(raw['architectural_acceptance'])

    def test_child_nonzero_not_recovered(self):
        got,raw,abort=self.durable(lambda result:None,17)
        self.assertEqual((got.status,got.returncode,raw['returncode']),('FAIL',17,17));self.assertTrue(abort.is_set())

    def test_late_abort_not_pass(self):
        result,_,_=self.artifact();abort=threading.Event()
        class Parent:
            def __init__(self):pass
            def _run_test(self,test,image):return result
        got=r.checked_runner(Parent,abort,lambda result:abort.set(),lambda name:None)()._run_test(SimpleNamespace(name=result.name),None)
        self.assertEqual(got.status,'CANCELLED')
        self.assertEqual(read(result.artifact_dir/'child_outcome.unvalidated.json')['returncode'],0)

    def pilot(self):
        child=dict(schema='UNVALIDATED_CHILD_OUTCOME_V1',architectural_acceptance=False,
            name=r.gates.PILOT_NAME,status='PASS',returncode=0,elapsed_s=1759.4446,reason='',artifact_dir='/fixture')
        result={k:child[k] for k in ('name','status','returncode','elapsed_s','reason','artifact_dir')}
        complete=dict(status=r.gates.PILOT_PASS,plan_sha256=r.gates.PILOT_PLAN,aborted=False,pins_unchanged=True,retries=0,results=[result])
        run=dict(status='COMPLETE',tests=[r.gates.PILOT_NAME],status_counts={'PASS':1},jobs=1,timeout_s=6300,completed_at='fixture')
        audit=dict(status=r.gates.PILOT_AUDIT_STATUS,accepted=True,cases=r.gates.PILOT_IDS,
            plan_sha256=r.gates.PILOT_PLAN,elf_sha256=r.gates.PILOT_ELF,image_sha256=r.IMAGE_SHA,
            pins_pre_post_unchanged=True,raw_logs_firsterror_veto_pass=True,child_outcome=child,child_returncode=0,
            strict=dict(status='NF2_CSV_ORACLE_PASS',cases=list(range(4))))
        return audit,complete,run,child

    def test_pilot_persisted_positive(self):r.gates.pilot_fields(*self.pilot())

    def test_actual_reference_schema_and_missing_last2(self):
        audit=read(r.gates.REFERENCE_AUDIT/'audit.json');ready=read(r.REF/'READY.json')
        r.gates.reference_fields(audit,ready)
        audit['groups']=audit['groups'][:-1]
        with self.assertRaises(ValueError):r.gates.reference_fields(audit,ready)
    def test_pilot_null_durable_rc(self):
        a,c,m,ch=self.pilot();ch['returncode']=None
        with self.assertRaises(ValueError):r.gates.pilot_fields(a,c,m,ch)
    def test_pilot_metadata_error(self):
        a,c,m,ch=self.pilot();c['status']='ERROR'
        with self.assertRaises(ValueError):r.gates.pilot_fields(a,c,m,ch)
    def test_pilot_console_not_terminal(self):
        a,c,m,ch=self.pilot();m['status']='RUNNING'
        with self.assertRaises(ValueError):r.gates.pilot_fields(a,c,m,ch)
    def test_pilot_wrong_image(self):
        a,c,m,ch=self.pilot();a['image_sha256']='wrong'
        with self.assertRaises(ValueError):r.gates.pilot_fields(a,c,m,ch)
    def test_pilot_abort(self):
        a,c,m,ch=self.pilot();c['aborted']=True
        with self.assertRaises(ValueError):r.gates.pilot_fields(a,c,m,ch)

    def test_deadline_keeps_last2_budget(self):
        r.deadline_gate(self.cases[8],100,3700)
        with self.assertRaises(ValueError):r.deadline_gate(self.cases[6],100,3700)
        with self.assertRaises(ValueError):r.deadline_gate(self.cases[8],101,3700)

    def test_fresh_plan_sha(self):
        common.save(self.root/'plan.json',dict(jobs=3));digest=sha(self.root/'plan.json')
        common.save(self.root/'plan.json',dict(jobs=4))
        with patch.object(r,'validate',side_effect=AssertionError('should not reach')):
            with self.assertRaises(ValueError):r.terminal_plan_gate(self.root,digest,r.IMAGE)

    def test_budget_drift_rejected(self):
        with patch.object(r,'sha',return_value=r.IMAGE_SHA),patch.object(r.checker,'scope',return_value=self.cases):
            p=dict(status='PREPARED_NOT_RUN',image=str(r.IMAGE),image_sha256=r.IMAGE_SHA,cases=deepcopy(self.cases),jobs=3,
                timeout_s=6300,worker_timeout_s=25200,service_timeout_s=27000,unit=r.UNIT,
                no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True)
            p['cases'][8]['timeout_s']=6300
            with self.assertRaises(ValueError):r.validate(p,r.IMAGE)

    def test_own_service(self):
        props=dict(Id=r.UNIT,LoadState='loaded',ActiveState='active',SubState='running',MainPID='10',
            ControlGroup='/user/'+r.UNIT,RuntimeMaxUSec='7h 30min',KillMode='control-group',Restart='no')
        r.owner_gate(props,'0::/user/'+r.UNIT,10)
        props['MainPID']='11'
        with self.assertRaises(ValueError):r.owner_gate(props,'0::/user/'+r.UNIT,10)

    def test_max3_and_firstfail_stops_queue(self):
        abort=threading.Event();entered=threading.Barrier(3);lock=threading.Lock();started=[];peak=[0];active=[0]
        root=self.root
        class Parent:
            def __init__(self):pass
            def _run_test(self,test,image):
                path=root/test.name
                if self.cancel_event.is_set():
                    return SimpleNamespace(name=test.name,status='CANCELLED',returncode=None,elapsed_s=0,reason='cancel',artifact_dir=path)
                with lock:
                    started.append(test.name);active[0]+=1;peak[0]=max(peak[0],active[0])
                entered.wait(timeout=5)
                if test.name!='0':
                    if not abort.wait(5):raise ValueError('Host cancellation timeout')
                with lock:active[0]-=1
                return SimpleNamespace(name=test.name,status='FAIL' if test.name=='0' else 'CANCELLED',
                    returncode=1,elapsed_s=.1,reason='host counterexample',artifact_dir=path)
        runner=r.checked_runner(Parent,abort,lambda result:None,lambda name:None)()
        with ThreadPoolExecutor(max_workers=r.JOBS) as pool:
            results=list(pool.map(lambda i:runner._run_test(SimpleNamespace(name=str(i)),None),range(10)))
        self.assertEqual(peak[0],3);self.assertEqual(set(started),{'0','1','2'})
        self.assertTrue(abort.is_set());self.assertFalse(any(x.status=='PASS' for x in results))

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('Fresh Host output only')
    a.out.mkdir();log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    (a.out/'log.txt').write_text(log.getvalue())
    pins={str(HERE/n):sha(HERE/n) for n in ('checker.py','gates.py','replay.py','test_host.py')}
    common.save(a.out/'status.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST_ONLY_NOT_DUT',
        tests=result.testsRun,failures=len(result.failures)+len(result.errors),pins=pins,
        reference_runs=0,DUT_runs=0,live_queries=0,full_oracle_host_reused=str(r.REF/'host01/status.json')))
    print(log.getvalue());return int(not result.wasSuccessful())

if __name__=='__main__':raise SystemExit(main())
