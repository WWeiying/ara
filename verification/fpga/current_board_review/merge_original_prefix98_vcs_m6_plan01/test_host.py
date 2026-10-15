#!/usr/bin/env python3
"""Host protocol fixtures with actual ELF PCs, not DUT or execution evidence."""
import argparse
import copy
import csv
import io
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
sys.dont_write_bytecode=True
import replay
from replay import checker as c
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')


def fixture(spec,model,fault=None):
    order=cycle=0
    def row(r,rd=0,value=0,address=0,rmask=0,wmask=0,wdata=0,event='retire'):
        nonlocal order,cycle
        result=dict(cycle=str(cycle),event=event,order=str(order),port='0',trans_id='0',
            pc=f"{r['pc']:x}",insn=r['insn'],rd=str(rd),rd_wdata=f'{value:x}',mem_addr=f'{address:x}',
            mem_rmask=f'{rmask:x}',mem_wmask=f'{wmask:x}',mem_wdata=f'{wdata:x}',trap='0')
        cycle+=1
        if event=='retire': order+=1
        return result
    def at(pc): return spec['instructions'][f'{pc:x}']
    aliases={5:'t0',10:'a0',11:'a1',12:'a2',13:'a3',14:'a4',15:'a5',16:'a6',17:'a7',28:'t3'}
    setters={n:next(r for r in spec['instructions'].values() if
        r['pc']<spec['capacity'][0]['pc'] and not c.is_csr(int(r['insn'],16)) and
        not c.is_rvv(int(r['insn'],16)) and
        re.match(r'(?:auipc|lui|li|addi|mv)\t'+alias+r'(?:,|$)',r['text']))
        for n,alias in aliases.items()}
    def setreg(n,v): return row(setters[n],rd=n,value=v)
    def vector(r,rd=0,value=0):
        from ara_verify.trace import is_vector_instruction
        if is_vector_instruction(int(r['insn'],16)):
            yield row(r,event='cvx_req')
            yield row(r,event='cvx_resp')
        yield row(r,rd=rd,value=value)
    for i,r in enumerate(spec['prelude'][:6]):
        if i in (1,2): yield setreg(5,spec['symbols']['trap_entry'] if i==1 else 0x6600)
        yield from vector(r,rd=(int(r['insn'],16)>>7)&31,value=128 if i==5 else 0)
    if fault=='unused_integer':
        r=next(r for r in spec['instructions'].values() if
               spec['unused_ranges'][0][0]<=r['pc']<spec['unused_ranges'][0][1] and r['text'].startswith('mv\t'))
        yield row(r)
    cap=spec['capacity']
    for i,r in enumerate(cap):
        yield from vector(r,rd=5 if i==0 else 10 if i==1 else 0,value=(1<<64)-1 if i==0 else 512 if i==1 else 0)
    if fault=='capacity_twice': yield row(cap[0],rd=5,value=(1<<64)-1)
    r=spec['prelude'][6]
    yield from vector(r,rd=(int(r['insn'],16)>>7)&31,value=64 if fault=='vlenb' else 128)
    if fault=='extra_csr': yield row(r,rd=15,value=128)
    for pc,addr,value,width in c.setup_events(spec,model):
        if fault=='rng' and addr==spec['addresses']['input']: value^=1
        if fault=='missing_setup' and addr==spec['addresses']['input']: continue
        yield row(at(pc),address=addr,wmask=((1<<width)-1)<<(addr%8),wdata=value)
    for _ in range(3584): yield row(at(spec['sites']['filter']))
    a=spec['addresses']
    for j,gold in enumerate(model['rows']):
        yield row(at(spec['sites']['filter']))
        for pc,addr,value,width in c.setup_events(spec,model,gold):
            wmask=((1<<width)-1)<<(addr%8)
            if j==0 and fault=='setup_be': wmask=1
            yield row(at(pc),address=addr,wmask=wmask,wdata=value)
        args=[a['input'],a['indices'],a['output']+2,gold['vl'],512,a['predicate'],0,gold['vstart']]
        if j==0 and fault=='pointer': args[1]=a['indices16']
        if j==0 and fault=='start': args[7]+=1
        for n,v in enumerate(args,10): yield setreg(n,v)
        for i,r in enumerate(spec['routine']):
            if j==0 and i==6 and fault=='interposed_integer': yield setreg(28,0)
            rr=dict(r)
            if j==0 and i==8 and fault=='target_encoding': rr['insn']='30880c57'
            rd,value=(5,gold['vl'] if i==5 else 512) if i in (0,5,10) else (0,0)
            if i==6: rd=28
            if i==9: rd,value=10,int(j==0 and fault=='vstart')
            yield from vector(rr,rd,value)
        if j==0 and fault=='duplicate_interior': yield row(spec['routine'][6],rd=28)
        for k,index in enumerate(list(range(1,513))+[0,513]):
            value=91 if index in (0,513) else gold['output'][index-1]
            pc=spec['sites']['output_read'] if 1<=index<=512 else spec['sites']['guard0' if index==0 else 'guard1']
            r=at(pc)
            rd=(int(r['insn'],16)>>7)&31
            if j==0 and index==513 and fault=='guard': value^=1
            if j==97 and index==512 and fault=='missing_final': continue
            if j==97 and index==512 and fault=='last_data': value^=1
            if j==17 and index==2 and fault=='tail': value^=1
            if j==32 and index==1 and fault=='prestart': value^=1
            if j==17 and index==1 and fault=='selected_source':
                assert value==model['indices'][0]
                value=model['input'][0]
            if j==29 and index==1 and fault=='gather_maskoff':
                assert gold['tuple'][4]==3 and gold['vstart']==0 and gold['vl']==1
                assert value==model['input'][0] and value!=91
                value=91
            if j==0 and index==1 and fault=='wrong_scalar_pc': r=setters[5]
            if j==0 and index==1 and fault=='wrong_pc_code': r=dict(r,insn='00000013')
            yield row(r,rd=rd,value=value,address=a['output']+2*index,rmask=3<<((a['output']+2*index)%8))
    yield row(spec['exit_store'],address=spec['exit_address'],wmask=255,wdata=int(fault=='exit'))
    yield row(spec['park'],rd=int(fault=='park'))


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger,_,_=c.common.image_context(IMAGE)
        cls.case,cls.spec=replay.scope()
        cls.model=c.source.model()
        cls.console='\n'.join(['BOARD_CASE_BEGIN '+c.NAME,'RVV_MERGE_PREFIX_PASS sew=16 cases=98 errors=0',
            'BOARD_CASE_PASS '+c.NAME,'BOARD_REPLAY_PASS',c.common.SUCCESS,'$finish'])

    def test_full98_actual_pc_fixture(self):
        from ara_verify.trace import validate_trace
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'synthetic.csv'
            rows=fixture(self.spec,self.model);first=next(rows)
            with p.open('w') as f:
                w=csv.DictWriter(f,fieldnames=list(first));w.writeheader();w.writerow(first);w.writerows(rows)
            generic=validate_trace(p)
            with p.open() as f: result=c.retirement(csv.DictReader(f),self.spec,self.model)
            self.assertEqual(result['target_hits'],98)
            self.assertEqual(result['actual_output_scalar_loads'],50372)
            self.assertEqual(result['retired_rows'],generic['retire_count'])
            self.assertEqual(result['unused_helper_retirements'],0)

    def test_discriminating_trace_negatives(self):
        for fault,reason in [
            ('unused_integer','Unused helper'),('capacity_twice','Capacity phase'),('extra_csr','CSR outside'),
            ('vlenb','vlenb'),('rng','initialization'),('missing_setup','initialization'),
            ('setup_be','initialization'),('pointer','arguments'),('start','arguments'),
            ('interposed_integer','Noncontiguous13'),('duplicate_interior','order/phase'),
            ('target_encoding','PC/code'),('vstart','vstart nonzero'),('guard','oracle mismatch'),
            ('missing_final','oracle PC/order'),('last_data','oracle mismatch'),('tail','oracle mismatch'),
            ('prestart','oracle mismatch'),('selected_source','oracle mismatch'),('gather_maskoff','oracle mismatch'),
            ('wrong_scalar_pc','Unexpected output'),('wrong_pc_code','PC/code'),('exit','CTRL exit'),('park','Post-exit')]:
            with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,reason):
                c.retirement(fixture(self.spec,self.model,fault),self.spec,self.model)

    def test_console(self):
        c.console_gate(self.console)
        for marker in ('RVV_PERMUTE_DETAIL op=4','RVV_MERGE_PREFIX_FAIL','BOARD_REPLAY_MISMATCH','ABORTED'):
            with self.subTest(marker=marker),self.assertRaisesRegex(ValueError,'veto'):
                c.console_gate(self.console+'\n'+marker)
        with self.assertRaises(ValueError): c.console_gate(self.console.replace('RVV_MERGE_PREFIX_PASS','absent'))

    def test_actual_partial_detail_monitor(self):
        import ara_verify.runner as engine
        line=(c.REF/'host/gather_maskoff.log').read_text().splitlines()[0]
        self.assertIn('RVV_PERMUTE_DETAIL op=4',line)
        partial=line.split(' expected=',1)[0]
        with tempfile.TemporaryDirectory() as tmp,patch.object(engine,'FAIL_RE',re.compile(engine.FAIL_RE.pattern+'|'+c.VETO.pattern,re.I)):
            code,elapsed,timeout,failed=engine._run_monitored([sys.executable,'-c',
                'import os,time;os.write(1,'+repr(partial.encode())+');time.sleep(30)'],
                Path(tmp),Path(tmp)/'host.log',10,threading.Event())
            self.assertTrue(failed);self.assertFalse(timeout);self.assertNotEqual(code,0);self.assertLess(elapsed,5)

    def test_plan_drift(self):
        plan=dict(status='PREPARED_NOT_RUN',image=str(IMAGE),image_sha256=replay.IMAGE_SHA,case=self.case,
            spec=self.spec,jobs=1,timeout_s=9000,service_timeout_s=10200,unit=replay.UNIT,
            no_build=True,no_retry=True,no_fsdb=True,launch_requirements=replay.LAUNCH_REQUIREMENTS,
            reference_ready_sha256=replay.READY_SHA,pins={str(Path(replay.__file__).resolve()):c.sha(Path(replay.__file__))})
        plan.update(reference_admission_sha256=replay.ADMISSION_SHA,reference_review_sha256=replay.REVIEW_SHA)
        replay.validate(plan,IMAGE)
        for field,value in [('timeout_s',9001),('jobs',2),('service_timeout_s',10800),('no_retry',False),
                            ('image_sha256','0'*64),('case',dict(self.case,sha256='0'*64))]:
            with self.subTest(field=field),self.assertRaises(ValueError): replay.validate(dict(plan,**{field:value}),IMAGE)

    def test_reference_admission_and_parent_authorization(self):
        with self.assertRaises(ValueError): replay.authorization_gate({},'a'*64,None,None)
        with tempfile.TemporaryDirectory() as tmp:
            review=Path(tmp)/'HOST_NOT_AUTHORIZATION.json'
            data=dict(decision='AUTHORIZE_MERGE_PREFIX98_ONCE',plan_sha256='a'*64,
                unit=replay.UNIT,budget_risk_accepted=True,reference_ready_sha256=replay.READY_SHA,
                reference_admission_sha256=replay.ADMISSION_SHA,reference_review_sha256=replay.REVIEW_SHA)
            c.common.save(review,data)
            replay.authorization_gate({},'a'*64,review,c.sha(review))
            for field,value in [('decision','NOT_AUTHORIZED'),('budget_risk_accepted',False),
                                ('reference_admission_sha256','0'*64),('reference_review_sha256','0'*64)]:
                c.common.save(review,dict(data,**{field:value}))
                with self.assertRaises(ValueError): replay.authorization_gate({},'a'*64,review,c.sha(review))
            with patch.object(replay,'read',return_value=dict(decision='PENDING')):
                with self.assertRaisesRegex(ValueError,'scope not accepted'): replay.accepted_reference()

    def test_fresh_disk_plan_after_expensive_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);p=out/'plan.json';c.common.save(p,dict(host=True));digest=c.sha(p)
            def drift(_): c.common.save(p,dict(host=False))
            with patch.object(replay,'validate'),patch.object(c.common,'image_context'),\
                 patch.object(c.common.base,'verify_pins',side_effect=drift):
                with self.assertRaisesRegex(ValueError,'Late disk plan SHA'):
                    replay.final_inputs(out,digest,IMAGE,{})

    def test_late_abort_during_validation(self):
        abort=threading.Event()
        class Parent:
            def __init__(self): pass
            def _run_test(self,*_): return SimpleNamespace(status='PASS',reason='',returncode=0)
        def check(_):
            def rows():
                for n,r in enumerate(fixture(self.spec,self.model)):
                    if n==2000: abort.set()
                    yield r
            c.retirement(rows(),self.spec,self.model)
        result=replay.checked_runner(Parent,abort,check)()._run_test(None,None)
        self.assertEqual(result.status,'CANCELLED');self.assertTrue(abort.is_set())

    def test_validation_exception_cancels(self):
        abort=threading.Event()
        class Parent:
            def __init__(self): pass
            def _run_test(self,*_): return SimpleNamespace(status='PASS',reason='')
        with self.assertRaisesRegex(ValueError,'bad raw'):
            replay.checked_runner(Parent,abort,Mock(side_effect=ValueError('bad raw')))()._run_test(None,None)
        self.assertTrue(abort.is_set())

    def test_complete_and_abort(self):
        abort=threading.Event();results=[SimpleNamespace(name=c.NAME,status='PASS',returncode=0)]
        meta=dict(status='COMPLETE',status_counts={'PASS':1},tests=[c.NAME],completed_at='host',jobs=1,
            timeout_s=9000,simv=self.ledger['simv'],commit_trace=True,code_coverage=False)
        replay.terminal_gate(results,meta,abort,self.ledger)
        for field,value in [('status','INTERRUPTED'),('tests',[]),('timeout_s',9001)]:
            with self.assertRaises(ValueError): replay.terminal_gate(results,dict(meta,**{field:value}),abort,self.ledger)
        abort.set()
        with self.assertRaisesRegex(ValueError,'Sticky abort'): replay.terminal_gate(results,meta,abort,self.ledger)

    def test_late_signal_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            terminal=dict(status=replay.PASS);abort=threading.Event()
            with patch.object(signal,'sigpending',return_value={signal.SIGTERM}):
                c.common.publish(Path(tmp),terminal,abort)
            self.assertEqual(c.read(Path(tmp)/'complete.json')['status'],'NOT_PASS')

    def test_pin_drift_and_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ELF';p.write_bytes(b'original');pins={str(p):c.sha(p)};p.write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError,'Pinned input drift'): c.common.base.verify_pins(pins)
        self.assertTrue(c.common.is_simv('renamed',['/private/simv']))
        self.assertTrue(c.common.is_simv('simv',['/private/renamed']))
        c.common.resource_math([],32*1024**3,c.HERE,1,23)
        for n,mem in [(24,64*1024**3),(0,31*1024**3)]:
            with self.assertRaises(ValueError): c.common.resource_math([dict(argv=['simv'])]*n,mem,c.HERE,1,0)

    def test_named_options_no_build(self):
        ledger,repo,(_,options,_,_)=c.common.image_context(IMAGE)
        opts=replay.build_options(options,repo,c.HERE/'HOST_ONLY',ledger,dry=True)
        self.assertTrue(opts.dry_run and opts.skip_build and opts.commit_trace)
        self.assertEqual((opts.jobs,opts.seed,opts.timeout_s),(1,1,9000))
        self.assertFalse(opts.code_coverage or opts.probe_kinds or opts.build_only)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='host01.json');args=p.parse_args()
    path=c.HERE/args.output;c.require(path.parent==c.HERE and not path.exists(),'Fresh owned Host output')
    log=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    c.common.save(path,dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),log=log.getvalue(),
        synthetic_protocol_fixture_not_DUT=True,trace_negative_subcases=24,script_sha256=c.sha(Path(__file__))))
    print(log.getvalue(),flush=True)
    raise SystemExit(not result.wasSuccessful())
