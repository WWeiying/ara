#!/usr/bin/env python3
"""Small case-specific protocol mutations; fixture is not DUT evidence."""
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
sys.dont_write_bytecode=True
import replay
from replay import checker as c
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')

def fixture(s,fault=None,tailones=False):
    code=s['code'];aliases={5:'t0',7:'t2',10:'a0',11:'a1',12:'a2',13:'a3',14:'a4',15:'a5',16:'a6',17:'a7'}
    def row(r,rd=0,value=0,address=0,rmask=0,wmask=0,wdata=0):
        return dict(pc=r['pc'],insn=int(r['insn'],16),rd=rd,value=value,address=address,rmask=rmask,wmask=wmask,wdata=wdata)
    setters={n:next(r for r in code.values() if r['pc']<s['capacity'][0]['pc'] and
        re.match(r'(?:auipc|lui|li|addi|mv)\t'+alias+r'(?:,|$)',r['text'])) for n,alias in aliases.items() if n!=7}
    def setreg(n,v):return row(setters[n],rd=n,value=v)
    for i,r in enumerate(s['prelude']):
        if i in (1,2):yield setreg(5,s['symbols']['trap_entry'] if i==1 else 0x6600)
        yield row(r,rd=(int(r['insn'],16)>>7)&31,value=128 if i==5 else 0)
    for i,r in enumerate(s['capacity']):yield row(r,rd=5 if i==0 else 10 if i==1 else 0,value=(1<<64)-1 if i==0 else 16 if i==1 else 0)
    if fault=='unused_internal':yield row(s['routines'][5][11])
    a=s['symbols'];golds=c.source.model()['rows']
    for j,g in enumerate(golds):
        for pc,addr,v,width in c.source.setup(s,g):
            if fault=='wrong_input' and j==0 and addr==a['a']:v^=1
            yield row(code[f'{pc:x}'],address=addr,wmask=((1<<width)-1)<<(addr%8),wdata=v)
        args=[a['a'],a['b'],a['output']+1,g['vl'],16,a['mask'],0,g['sticky']]
        if fault=='pointer' and j==0:args[1]=a['a']
        for n,v in enumerate(args,10):yield setreg(n,v)
        delta=2 if g['op']==4 else 0;rr=s['routines'][g['op']]
        for i,r in enumerate(rr):
            rd=value=addr=rmask=0
            if i==0:rd=30
            if i in (1,6+delta,14+delta):rd,value=5,g['vl'] if i==6+delta else 16
            if g['op']==4 and i==6:rd,addr,rmask=7,a['b'],3<<(a['b']%8)
            if i==9+delta:rd,value=10,int(fault=='vstart' and j==264)
            if i==10+delta:
                rd,value=6,g['flags']
                if fault=='tail_nv' and j==264:value|=16
                if fault=='lost_sticky' and j==1:value=0
            if i==11+delta:rd,value=6,g['flags']<<32
            if i==12+delta:rd,value=10,g['flags']<<32
            r=dict(r)
            if fault=='target_encoding' and j==264 and i==8+delta:r['insn']='60805c57'
            yield row(r,rd,value,addr,rmask)
        if fault=='duplicate_interior' and j==0:yield row(rr[11],rd=6)
        vals=[]
        for k in range(2):
            byte=0
            for b in range(8):
                index=k*8+b;allowed=g['allowed'][index]
                v=1 if tailones and 1 in allowed and index>=g['vl'] and g['vl'] else ((91>>b)&1 if (91>>b)&1 in allowed else allowed[0])
                byte|=v<<b
            vals.append(byte)
        for k in range(18):
            if fault=='missing_last_bit' and j==264 and k==15:continue
            value=vals[k//8] if k<16 else 91
            if fault=='wrong_raw_zero_eq' and j==264 and k==0:value|=1
            if fault=='vl0_old' and j==0 and k==0:value^=1
            if fault=='guard' and j==264 and k==17:value^=1
            pc=s['sites']['bits'] if k<16 else s['sites']['guard0' if k==16 else 'guard1']
            r=code[f'{pc:x}'];addr=a['output']+(1+k//8 if k<16 else 0 if k==16 else 3)
            yield row(r,rd=(int(r['insn'],16)>>7)&31,value=value,address=addr,rmask=1<<(addr%8))
    yield row(s['exit_store'],address=s['exit_address'],wmask=255,wdata=int(fault=='exit'))
    yield row(s['park'])

class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c.common.image_context(IMAGE)
        cls.case,cls.s=replay.scope()
    def test_original265_positive_and_allowed_tail(self):
        for tail in (False,True):
            result=c.source.audit(fixture(self.s,tailones=tail),self.s)
            self.assertEqual((result['target_calls'],result['helper_instructions'],result['full_result_bit_checks'],result['guard_checks']),(265,4587,4240,530))
    def test_specific_negatives(self):
        for fault in ('wrong_raw_zero_eq','tail_nv','lost_sticky','vl0_old','guard','vstart','missing_last_bit',
                      'duplicate_interior','unused_internal','target_encoding','wrong_input','pointer','exit'):
            with self.subTest(fault=fault),self.assertRaises(ValueError):c.source.audit(fixture(self.s,fault),self.s)
    def test_console_and_real_partial_detail_monitor(self):
        console='\n'.join(['BOARD_CASE_BEGIN '+c.NAME,'RVV_FP_COMPARE_PASS sew=16 cases=265 errors=0','BOARD_CASE_PASS '+c.NAME,'BOARD_REPLAY_PASS',c.common.SUCCESS,'$finish'])
        c.console_gate(console)
        with self.assertRaises(ValueError):c.console_gate(console.replace('cases=265','cases=1'))
        import ara_verify.runner as engine
        actual=(c.REF/'host01/mutation2.log').read_text().splitlines()[0]
        self.assertIn('RVV_FP_COMPARE_DETAIL',actual)
        with tempfile.TemporaryDirectory() as tmp,patch.object(engine,'FAIL_RE',re.compile(engine.FAIL_RE.pattern+'|'+c.VETO.pattern,re.I)):
            rc,elapsed,timeout,failed=engine._run_monitored([sys.executable,'-c','import os,time;os.write(1,'+repr(actual.split(' actual_flags')[0].encode())+');time.sleep(30)'],Path(tmp),Path(tmp)/'host.log',10,threading.Event())
            self.assertTrue(failed);self.assertFalse(timeout);self.assertNotEqual(rc,0);self.assertLess(elapsed,5)
    def test_fresh_plan_and_late_abort(self):
        abort=threading.Event()
        class Parent:
            def _run_test(self,*_):return SimpleNamespace(status='PASS',reason='')
        def validation(_):abort.set()
        result=replay.worker.checked_runner(Parent,abort,validation)()._run_test(None,None)
        self.assertEqual(result.status,'CANCELLED')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);p=out/'plan.json';c.common.save(p,{'host':True});digest=c.sha(p)
            def drift(_):c.common.save(p,{'host':False})
            with patch.object(replay.worker,'validate'),patch.object(c.common,'image_context'),patch.object(c.common.base,'verify_pins',side_effect=drift):
                with self.assertRaisesRegex(ValueError,'Late disk plan'):replay.worker.final_inputs(out,digest,IMAGE,{})
    def test_pin_budget_and_launch_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'elf';p.write_bytes(b'old');pins={str(p):c.sha(p)};p.write_bytes(b'new')
            with self.assertRaises(ValueError):c.common.base.verify_pins(pins)
        with self.assertRaises(ValueError):replay.authorization_gate({},'0'*64,None,None)
        ledger,repo,(_,options,_,_)=c.common.image_context(IMAGE)
        opt=replay.worker.build_options(options,repo,c.HERE/'HOST_ONLY',ledger,True)
        self.assertTrue(opt.skip_build and opt.dry_run and opt.commit_trace)
        self.assertEqual((opt.jobs,opt.timeout_s),(1,5400))

if __name__=='__main__':
    path=c.HERE/'host02.json';c.require(not path.exists(),'Preserve Host output')
    t=time.monotonic()
    with (c.HERE/'host02.log').open('x') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Gates))
    c.common.save(path,dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),elapsed_s=time.monotonic()-t,script_sha256=c.sha(Path(__file__)),
        synthetic_protocol_positives=2,case_specific_negative_subtests=13,no_dut=True))
    print(c.read(path));raise SystemExit(not result.wasSuccessful())
