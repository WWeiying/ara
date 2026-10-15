"""Small worker metadata, durable-outcome, monitor and protocol Host gates."""
import copy
import csv
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
import replay as app
from replay import checker as c
import csv_check
sys.path.insert(0,str(c.G.parents[1]))
import ara_verify.runner as engine
from ara_verify.trace import validate_trace

class Host(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=app.HERE,prefix='host_tmp_');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'work').mkdir()
        self.case,self.spec=app.scope();self.ledger=dict(simv='/synthetic/simv',files={'host':'only'})
        shutil.copyfile(self.case['elf'],self.root/'input.elf')
        (self.root/'console.log').write_text('NEGATIVE_STRIDE_STORE_SINGLE_PASS\n'+c.common.SUCCESS+'\n$finish\n')
        (self.root/'work/run.vcs.log').write_text('host metadata only\n')
        (self.root/'commit_trace.csv').write_text('Host fixture is not a DUT trace\n')
        self.write('trace_summary.json',dict(status='VALID'))
        self.command=dict(cwd=str(self.root/'work'),command=[self.ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
            '+PRELOAD='+str(self.root/'input.elf'),'+TESTCASE='+app.NAME,'+NO_FSDB','+COMMIT_TRACE='+str(self.root/'commit_trace.csv')])
        self.write('command.json',self.command)
        self.write('inputs.json',dict(binary=dict(source=self.case['elf'],path=str(self.root/'input.elf'),sha256=self.case['sha256']),
                                     simv=dict(path=self.ledger['simv'],image_sha256=self.ledger['files'])))
        self.result=SimpleNamespace(name=app.NAME,status='PASS',returncode=0,elapsed_s=1.25,reason='',artifact_dir=self.root)
    def write(self,n,v):(self.root/n).write_text(json.dumps(v))
    def check(self):c.common.check_artifacts(self.result,c.runtime_case(self.case),self.ledger)
    def test_runtime_history(self):
        before=copy.deepcopy(self.case);self.check();self.assertEqual(before,self.case)
        with self.assertRaises(ValueError):c.common.check_artifacts(self.result,self.case,self.ledger)
        self.case['original_name']='wrong_original'
        with self.assertRaises(ValueError):self.check()
    def test_wrong_seed_preload_testcase_cwd(self):
        for i,v in ((3,'+ntb_random_seed=2'),(4,'+PRELOAD='+self.case['elf']),(5,'+TESTCASE='+app.HISTORICAL)):
            b=copy.deepcopy(self.command);b['command'][i]=v;self.write('command.json',b)
            with self.assertRaises(ValueError):self.check()
        self.write('command.json',dict(self.command,cwd=str(self.root)))
        with self.assertRaises(ValueError):self.check()
    def test_missing_oracle_rawfail_elf(self):
        for text in ('Core Test *** SUCCESS *** (tohost = 0)\n$finish','NEGATIVE_STRIDE_STORE_SINGLE_FAIL','BOARD_REPLAY_MISMATCH case0'):
            with self.assertRaises(ValueError):c.console_gate(text)
        (self.root/'input.elf').write_bytes(b'drift')
        with self.assertRaises(ValueError):self.check()
    def test_durable_monitor_before_parent_checker_throw(self):
        root=self.root;supplied=self.result
        def fake_monitor(*args):return 0,1.25,False,False
        old=engine._run_monitored;engine._run_monitored=fake_monitor
        self.addCleanup(setattr,engine,'_run_monitored',old)
        class Parent:
            def _run_test(self,*_):
                engine._run_monitored(['fake'],root/'work',root/'console.log',app.TIMEOUT)
                self_result=c.read(root/'monitor_outcome.unvalidated.json')
                if self_result['returncode']!=0:raise ValueError('monitor record missing')
                return supplied
        def fail(_):
            self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['returncode'],0)
            raise ValueError('injected checker failure')
        abort=threading.Event()
        with self.assertRaisesRegex(ValueError,'injected'):
            app.checked_runner(Parent,abort,fail)()._run_test(None,None)
        self.assertTrue(abort.is_set());self.assertFalse(c.read(root/'monitor_outcome.unvalidated.json')['architectural_acceptance'])
        self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['returncode'],0)
    def test_durable_timeout_numeric(self):
        app.durable_monitor(lambda *args:(-15,5400.1,True,False))([],self.root/'work',self.root/'console.log',app.TIMEOUT)
        r=c.read(self.root/'monitor_outcome.unvalidated.json')
        self.assertEqual(r['returncode'],-15);self.assertTrue(r['timed_out'])
    def test_abort_during_check_sticky(self):
        supplied=self.result
        class Parent:
            def _run_test(self,*_):return supplied
        abort=threading.Event()
        r=app.checked_runner(Parent,abort,lambda _:abort.set())()._run_test(None,None)
        self.assertEqual(r.status,'CANCELLED');self.assertTrue(abort.is_set())
    def test_actual_partial_marker_monitor(self):
        old=engine.FAIL_RE;engine.FAIL_RE=re.compile(old.pattern+'|'+c.VETO.pattern,re.I)
        self.addCleanup(setattr,engine,'FAIL_RE',old)
        command=[sys.executable,'-c','import os,time;os.write(1,b"BOARD_REPLAY_MISMATCH case0");time.sleep(15)']
        self.write('command.json',dict(command=command,cwd=str(self.root/'work')))
        rc,elapsed,timeout,failed=app.durable_monitor(engine._run_monitored)(command,self.root/'work',self.root/'partial.log',10)
        self.assertTrue(failed);self.assertFalse(timeout);self.assertLess(elapsed,5);self.assertIsInstance(rc,int)
        self.assertTrue(c.read(self.root/'monitor_outcome.unvalidated.json')['failure_seen'])
    def test_budget_original66_and_plan_drift(self):
        image=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
        data=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=app.IMAGE_SHA,case=self.case,spec=self.spec,
            jobs=1,timeout_s=5400,worker_timeout_s=7200,service_timeout_s=7800,unit=app.UNIT,no_retry=True,no_build=True,no_fsdb=True,
            reference_ready_sha256=app.READY_SHA,adapter_review_pins=app.AUDIT_PINS,
            pins={**c.read(c.REF/'READY.json')['pins'],str(Path(app.__file__)):c.sha(Path(app.__file__))})
        app.validate(data,image)
        for k,v in (('jobs',2),('timeout_s',3600),('worker_timeout_s',7800),('service_timeout_s',7200),('image_sha256','0'*64),('no_fsdb',False)):
            b=copy.deepcopy(data);b[k]=v
            with self.assertRaises(ValueError):app.validate(b,image)
        b=copy.deepcopy(data);del b['pins'][next(iter(c.read(c.REF/'READY.json')['pins']))]
        with self.assertRaises(ValueError):app.validate(b,image)
        self.write('plan.json',data)
        with self.assertRaisesRegex(ValueError,'Plan file drift'):
            app.worker.final_inputs(self.root,'0'*64,image,{})
    def test_no_parent_launch_permission(self):
        with self.assertRaises(ValueError):app.authorization_gate({},'0'*64,None,None)
    def test_actual_entry_scope_not_load(self):
        app.accepted_adapter();original=app.read
        actual=original(app.AUDIT/'ENTRY.json')
        for key,value in (('decision','PENDING'),('source_name','wrong_load'),('reference_scalar_checks',17274),
                          ('ready_sha256','0'*64),('dut_launch_authorized_by_review',True)):
            bad=dict(actual,**{key:value})
            with patch.object(app,'read',side_effect=lambda p:bad if p==app.AUDIT/'ENTRY.json' else original(p)):
                with self.assertRaises(ValueError):app.accepted_adapter()
    def test_worker_deadline_sticky_publication(self):
        abort=threading.Event();timer=threading.Timer(30,abort.set);timer.start()
        app.quiesce_deadline(timer,abort,time.monotonic()-1)
        self.assertTrue(abort.is_set())
        terminal=dict(status=app.worker.PASS)
        c.common.publish(self.root,terminal,abort)
        self.assertEqual(c.read(self.root/'complete.json')['status'],'NOT_PASS')
    def test_protocol_validator_negatives(self):
        fields=csv_check.FIELDS
        events=[('cvx_req',0,0,0),('arch_start',0,0,0),('uop_alloc',0,0,0),('uop_done',0,0,0),('cvx_resp',0,0,1),
                ('cvx_req',1,1,0),('arch_start',1,1,0),('uop_alloc',1,1,0),('uop_done',1,1,0),('cvx_resp',1,1,0),('retire',0,-1,0)]
        rows=[]
        for i,(event,order,tid,trap) in enumerate(events):
            r={k:'0' for k in fields};r.update(cycle=str(i),event=event,order=str(order),trans_id=str(tid),insn='09c55c27',trap=str(trap));rows.append(r)
        def validate(items):
            with (self.root/'protocol.csv').open('w') as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(items)
            return validate_trace(self.root/'protocol.csv')
        good=validate(rows);self.assertEqual(good['cvx_exception_count'],1);self.assertEqual(good['backend_uop_done_count'],2)
        for name,index in (('missing_uop_done',8),('missing_response',9),('missing_arch',6)):
            with self.subTest(name=name),self.assertRaises(Exception):validate(rows[:index]+rows[index+1:])

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    c.require(not args.out.exists(),'Fresh Host report only')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    pins={str(p):c.sha(p) for p in (Path(__file__),Path(app.__file__),Path(c.__file__),Path(csv_check.__file__),
                                  Path(app.worker.__file__),Path(app.outcome.__file__))}
    c.common.save(args.out,dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),pins=pins))
    raise SystemExit(not result.wasSuccessful())
