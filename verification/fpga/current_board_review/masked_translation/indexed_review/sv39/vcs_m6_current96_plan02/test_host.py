#!/usr/bin/env python3
"""Synthetic Host gates only; no DUT, reference replay, service or capacity query."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
import replay as r
from checker import HERE, common, read, sha
import checker as c


def contract(cases):
    return dict(status='PREPARED_NOT_RUN',image=str(r.IMAGE),image_sha256=c.IMAGE_SHA,cases=copy.deepcopy(cases),
        jobs=4,timeout_s=2400,group_timeout_s=2700,worker_timeout_s=16200,service_timeout_s=16800,unit=r.UNIT,
        no_build=True,no_retry=True,no_fsdb=True,no_coverage=True,stop_first_fail=True,reserved_slots=0,
        old_manifest_sha256=c.READY_SHA,old_acceptance_sha256=c.AUDIT_SHA,nf2_prerequisite=r.nf2_gate.contract())


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cases=c.scope()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HERE,prefix='host_synthetic_')
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def reject(self,fn,*args):
        with self.assertRaises((ValueError,KeyError,OSError,TypeError)):fn(*args)

    def test_exact24_96_scope(self):
        r.validate_contract(contract(self.cases),self.cases)
        self.assertEqual(sum(x['checks'] for x in self.cases),284816)
        self.assertEqual(sum(x['checkpoints'] for x in self.cases),168)

    def test_wrong_runtime_id(self):
        p=contract(self.cases);p['cases'][0]['id']='historical_source';self.reject(r.validate_contract,p,self.cases)

    def test_wrong_image(self):
        p=contract(self.cases);p['image_sha256']='0'*64;self.reject(r.validate_contract,p,self.cases)

    def test_wrong_elf(self):
        p=contract(self.cases);p['cases'][0]['sha256']='0'*64;self.reject(r.validate_contract,p,self.cases)

    def test_missing_member(self):
        p=contract(self.cases);p['cases'].pop();self.reject(r.validate_contract,p,self.cases)

    def test_reordered_predecessor(self):
        p=contract(self.cases);p['cases'][0]['trials'].reverse();self.reject(r.validate_contract,p,self.cases)

    def test_duplicate_member(self):
        p=contract(self.cases);p['cases'][1]=p['cases'][0];self.reject(r.validate_contract,p,self.cases)

    def test_unmasked_historical_label_not_runtime(self):
        x=c.runtime_case(self.cases[0]);self.assertEqual(x['original_name'],'nf7_g00')
        self.assertEqual(self.cases[0]['original_name'],'rvv_fault_replay_segment_nf7_indexed_e32_mf2')

    def test_budgets_coverage_fsdb_retry(self):
        for k,v in [('jobs',5),('timeout_s',2401),('group_timeout_s',2800),('service_timeout_s',17000),
                    ('no_coverage',False),('no_fsdb',False),('no_retry',False),('no_build',False)]:
            with self.subTest(k=k):
                p=contract(self.cases);p[k]=v;self.reject(r.validate_contract,p,self.cases)

    def test_missing_oracle(self):
        self.reject(c.observer_gate,{},self.cases[0])
        x=self.cases[0]
        report=dict(status='NF7_CSV_ORACLE_PASS',trials=x['trials'],checks=x['checks'],
                    checkpoints=[None]*x['checkpoints'],traps=[None]*x['traps'])
        c.observer_gate(report,x)
        for k,v in [('checks',x['checks']-1),('trials',[0,1,2]),('checkpoints',[]),('traps',[])]:
            bad=copy.deepcopy(report);bad[k]=v;self.reject(c.observer_gate,bad,x)

    def test_unchanged_checker_empty_trace_rejected(self):
        # Import only; no existing raw trace is opened.
        observer=r.load('nf7_host_observer',HERE/'observer.py');old=observer.csv_oracle
        d=Path(self.cases[0]['source'])
        check=old.Checker(read(d/'soc.symbols.json'),read(d/'cases.json'),read(d/'status.json'),
                          read(Path(self.cases[0]['ledger'])))
        self.reject(check.finish)

    def test_pass_plus_fail(self):
        positive='IX_SV39_PASS\n'+common.SUCCESS+'\n$finish\n';c.log_gate(positive)
        for text in ['IX_SV39_FAIL','RVV_NF7_FAIL','FAIL','Error-[x]','Fatal:bad','Traceback']:
            with self.subTest(text=text):self.reject(c.log_gate,positive+text)

    def synthetic(self):
        root=self.root;work=root/'work';work.mkdir()
        (root/'input.elf').write_bytes(b'SYNTHETIC_NOT_EXECUTABLE')
        case=dict(self.cases[0],elf=str(root/'original.elf'),sha256=sha(root/'input.elf'))
        image=dict(simv='/synthetic/simv',files={'/synthetic/simv':'not_real'})
        cmd=[image['simv'],'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),
             '+TESTCASE=nf7_g00','+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')]
        common.save(root/'command.json',dict(command=cmd,cwd=str(work)))
        common.save(root/'inputs.json',dict(binary=dict(sha256=case['sha256'],source=case['elf'],
            path=str(root/'input.elf')),simv=dict(path=image['simv'],image_sha256=image['files'])))
        (root/'console.log').write_text('IX_SV39_PASS\n'+common.SUCCESS+'\n$finish\n')
        (work/'run.vcs.log').write_text('simulation completed\n')
        (root/'commit_trace.csv').write_text('SYNTHETIC_NOT_AN_ORACLE\n')
        common.save(root/'trace_summary.json',dict(status='VALID'))
        result=NS(name='nf7_g00',status='PASS',returncode=0,elapsed_s=1.25,artifact_dir=root,reason=None)
        return result,case,image,cmd

    def test_runtime_command_positive_and_wrong_id(self):
        result,case,image,cmd=self.synthetic()
        common.check_artifacts(result,c.runtime_case(case),image)
        cmd[5]='+TESTCASE='+case['original_name']
        common.save(self.root/'command.json',dict(command=cmd,cwd=str(self.root/'work')))
        self.reject(common.check_artifacts,result,c.runtime_case(case),image)

    def test_private_image_mismatch(self):
        result,case,image,_=self.synthetic();image['simv']='/wrong/simv'
        self.reject(common.check_artifacts,result,c.runtime_case(case),image)

    def test_private_elf_mismatch(self):
        result,case,image,_=self.synthetic();(self.root/'input.elf').write_bytes(b'changed')
        self.reject(common.check_artifacts,result,c.runtime_case(case),image)

    def test_real_artifact_missing_oracle(self):
        result,case,image,cmd=self.synthetic()
        r.persist_child(cmd,self.root/'work',(0,1.25,False,False))
        # The synthetic trace cannot pass the actual unchanged oracle.
        import time
        self.reject(c.artifacts,result,case,image,time.monotonic()+10)
        report=read(self.root/'observer.json');self.assertEqual(report['status'],'NF7_CSV_NOT_PASS')

    def outcome_then_error(self,code):
        result,case,image,cmd=self.synthetic();abort=threading.Event()
        def actual_monitor(*_):return (code,1.25,False,False)
        def runner_postcheck():
            r.monitored(actual_monitor,abort)(cmd,self.root/'work',self.root/'console.log',2400)
            raise ValueError('synthetic generic postcheck error before TestResult')
        self.reject(runner_postcheck)
        record=read(self.root/'child_outcome.unvalidated.json')
        self.assertEqual(record['returncode'],code);self.assertIs(type(record['returncode']),int)
        self.assertFalse(record['architectural_acceptance'])
        self.assertEqual(record['command_sha256'],sha(self.root/'command.json'))

    def test_postcheck_error_preserves_17(self):self.outcome_then_error(17)
    def test_postcheck_error_preserves_0(self):self.outcome_then_error(0)

    def test_command_read_error_still_preserves_numeric(self):
        (self.root/'work').mkdir();r.persist_child(['not executed'],self.root/'work',(17,1.0,False,False))
        x=read(self.root/'child_outcome.unvalidated.json')
        self.assertEqual(x['returncode'],17);self.assertIn('command_identity_error',x)

    def test_record_not_overwritten(self):
        (self.root/'work').mkdir();r.persist_child([],self.root/'work',(17,1.0,False,False))
        self.reject(r.persist_child,[],self.root/'work',(0,1.0,False,False))
        self.assertEqual(read(self.root/'child_outcome.unvalidated.json')['returncode'],17)

    def checked(self,check,status='PASS',code=0):
        abort=threading.Event();result=NS(status=status,returncode=code,reason=None)
        class Parent:
            def _run_test(self,*_):return result
        cls=r.frozen.checked_runner(Parent,abort,lambda result:check(result,abort),lambda _:None)
        got=cls()._run_test(NS(name='nf7_g00'),None);return got,abort

    def test_strict_error_retains_exit0_but_rejects(self):
        def fail(*_):raise ValueError('postcheck')
        result,abort=self.checked(fail)
        self.assertEqual((result.status,result.returncode),('FAIL',0));self.assertTrue(abort.is_set())

    def test_numeric17_not_reclassified(self):
        result,abort=self.checked(lambda *_:self.fail('must not check failed child'),'FAIL',17)
        self.assertEqual((result.status,result.returncode),('FAIL',17));self.assertTrue(abort.is_set())

    def test_late_abort(self):
        result,abort=self.checked(lambda _,a:a.set())
        self.assertEqual(result.status,'CANCELLED');self.assertTrue(abort.is_set())

    def test_late_terminal_abort(self):
        abort=threading.Event();abort.set();end=dict(status=r.PASS)
        common.publish(self.root,end,abort)
        self.assertEqual(read(self.root/'complete.json')['status'],'NOT_PASS')

    def test_direct_owner(self):
        props=dict(Id=r.UNIT,LoadState='loaded',ActiveState='active',SubState='running',MainPID='123',
            ControlGroup='/user.slice/'+r.UNIT,RuntimeMaxUSec='4h 40min',KillMode='control-group',Restart='no')
        group='0::'+props['ControlGroup'];r.owner_gate(props,group,123)
        for k,v in [('MainPID','124'),('KillMode','process'),('Restart','always'),('RuntimeMaxUSec','9h')]:
            p=dict(props);p[k]=v;self.reject(r.owner_gate,p,group,123)

    def test_resource_arithmetic_only(self):
        live=[dict(argv=['/not-run/simv'])]*20
        common.resource_math(live,32*1024**3,self.root,4,0)
        self.reject(common.resource_math,live,32*1024**3,self.root,4,1)
        self.reject(common.resource_math,[],32*1024**3-1,self.root,4,0)

    def test_no_launch_without_new_authorization(self):
        with patch.object(common,'resources',side_effect=AssertionError('No resource query')):
            self.reject(r.run,self.root,None,False,None,None)
            self.reject(r.authorization,'digest',None,None)

    def test_pin_drift(self):
        p=self.root/'input';p.write_text('before');pins={str(p):sha(p)}
        common.base.verify_pins(pins);p.write_text('after');self.reject(common.base.verify_pins,pins)


def main():
    out=HERE/'host01';out.mkdir(exist_ok=False)
    stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
    import test_nf2_gate
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(test_nf2_gate.NF2Gate))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    text=stream.getvalue();(out/'log.txt').write_text(text);print(text,end='')
    pins={str(HERE/n):sha(HERE/n) for n in ('checker.py','observer.py','replay.py','test_host.py','nf2_gate.py','test_nf2_gate.py','README.md')}
    for m in list(sys.modules.values()):
        p=getattr(m,'__file__',None)
        if p and Path(p).is_file() and str(Path(p).resolve()).startswith('/home/wangwy/'):
            pins[str(Path(p).resolve())]=sha(Path(p))
    failures=len(result.failures)+len(result.errors)
    common.save(out/'status.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'HOST_NOT_PASS',
        tests=result.testsRun,failures=failures,exit_code=0 if result.wasSuccessful() else 1,pins=pins,
        log_sha256=sha(out/'log.txt'),synthetic_only=True,DUT=False,reference_execution=False,resource_queries=False))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
