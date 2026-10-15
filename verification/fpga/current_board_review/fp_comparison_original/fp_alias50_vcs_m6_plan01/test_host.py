"""Focused alias50 source-data/real-code witnesses and mature numeric-first paths."""
import copy
import csv
import io
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode=True
import replay
from replay import checker as c
from newscope import *

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
    for i,r in enumerate(s['capacity']):yield row(r,rd=5 if i==0 else 10 if i==1 else 0,value=(1<<64)-1 if i==0 else 512 if i==1 else 0)
    if fault=='unused_internal':yield row(s['routines'][1][11])
    a=s['symbols'];golds=c.source.model()['rows']
    for j,g in enumerate(golds):
        if fault=='skip_predecessor' and j==20:continue
        for pc,addr,v,width in c.source.setup(s,g):
            if fault=='wrong_input' and j==0 and addr==a['a']:v^=1
            yield row(code[f'{pc:x}'],address=addr,wmask=((1<<width)-1)<<(addr%8),wdata=v)
        args=[a['a'],a['b'],a['output']+1,g['vl'],512,a['mask'],0,g['sticky']]
        if fault=='pointer' and j==0:args[1]=a['a']
        for n,v in enumerate(args,10):yield setreg(n,v)
        delta=0;rr=s['routines'][g['op']]
        for i,r in enumerate(rr):
            rd=value=addr=rmask=0
            if i==0:rd=30
            if i in (1,5,13):rd,value=5,g['vl'] if i==5 else 512
            if i==8:rd,value=10,int(fault=='vstart' and j==49)
            if i==9:
                rd,value=6,g['flags']
                if fault=='tail_nv' and j==16:value^=16
                if fault=='lost_sticky' and j==1:value=0
                if fault=='masked_flags' and j==39:value=1
            if i==10:rd,value=6,g['flags']<<32
            if i==11:rd,value=10,g['flags']<<32
            r=dict(r)
            if fault=='target_encoding' and j==49 and i==7:r['insn']='60881457'
            if fault=='missing_restore' and j==49 and i==12:continue
            if fault=='unknown_saved' and j==0 and i==0:rd=0
            yield row(r,rd,value,addr,rmask)
        if fault=='duplicate_interior' and j==0:yield row(rr[11],rd=6)
        vals=[]
        for k in range(64):
            byte=0
            for b in range(8):
                index=k*8+b;allowed=g['allowed'][index]
                v=1 if tailones and 1 in allowed and index>=g['vl'] and g['vl'] else ((g['a'][index//16]>>(index%16))&1 if (g['a'][index//16]>>(index%16))&1 in allowed else allowed[0])
                byte|=v<<b
            vals.append(byte)
        for k in range(514):
            if fault=='missing_last_bit' and j==49 and k==511:continue
            value=vals[k//8] if k<512 else 91
            if fault=='wrong_raw_zero_eq' and j==49 and k==0:value^=1
            if fault=='predecessor49_bit511' and j==48 and k==511:value^=128
            if fault=='last_active511' and j==49 and k==511:value^=128
            if fault=='vl0_old' and j==0 and k==0:value^=1
            if fault=='guard' and j==49 and k==513:value^=1
            pc=s['sites']['bits'] if k<512 else s['sites']['guard0' if k==512 else 'guard1']
            r=code[f'{pc:x}'];addr=a['output']+(1+k//8 if k<512 else 0 if k==512 else 65)
            yield row(r,rd=(int(r['insn'],16)>>7)&31,value=value,address=addr,rmask=1<<(addr%8))
    yield row(s['exit_store'],address=s['exit_address'],wmask=255,wdata=int(fault=='exit'))
    yield row(s['park'])


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger,cls.repo,cls.framework=c.common.image_context(IMAGE)
        cls.case=replay.cases()[0];cls.s=c.specification(Path(cls.case['elf']))

    def test_full_original50_positive_and_tail_policy(self):
        for tail in (False,True):
            result=c.source.audit(fixture(self.s,tailones=tail),self.s)
            self.assertEqual((result['target_calls'],result['helper_instructions'],result['full_result_bit_checks'],
                              result['guard_checks'],result['actual_initialization_stores']),(50,800,25600,100,64100))

    def test_historical_active_bits_predecessors_flags_and_guard_negatives(self):
        faults=('wrong_raw_zero_eq','last_active511','predecessor49_bit511','tail_nv','lost_sticky','masked_flags',
                'vl0_old','guard','vstart','missing_last_bit','duplicate_interior','unused_internal',
                'target_encoding','wrong_input','pointer','exit','skip_predecessor','missing_restore','unknown_saved')
        for fault in faults:
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                c.source.audit(fixture(self.s,fault),self.s)

    def test_all_unused_helper_interiors(self):
        for rr in self.s['routines'][1:]:
            for r in rr:
                with self.assertRaisesRegex(ValueError,'Unused helper/trap'):
                    c.source.audit([dict(pc=r['pc'],insn=int(r['insn'],16))],self.s)

    def test_console_veto_identity_and_full_count(self):
        text='\n'.join(['BOARD_CASE_BEGIN '+NAME,MARKER,'BOARD_CASE_PASS '+NAME,'BOARD_REPLAY_PASS',c.common.SUCCESS,'$finish'])
        c.console_gate(text)
        for bad in (text+'\nFAIL',text+'\nRVV_FP_COMPARE_DETAIL op=0',text.replace(NAME,HISTORICAL),
                    text+'\n'+MARKER,text.replace('cases=50','cases=49'),text.replace('$finish','')):
            with self.assertRaises(ValueError):c.console_gate(bad)

    def test_six_event_protocol_with_actual_op0_machine_code(self):
        from ara_verify.trace import is_vector_instruction,validate_trace,TraceValidationError
        rows=[];cycle=order=arch=0
        for r in self.s['routines'][0]:
            ins=int(r['insn'],16)
            def item(event,ordinal):
                nonlocal cycle
                v=dict(cycle=str(cycle),event=event,order=str(ordinal),port='0',trans_id='0',
                       pc=f"{r['pc']:x}",insn=f'{ins:x}',rd='0',rd_wdata='0',mem_addr='0',
                       mem_rmask='0',mem_wmask='0',mem_wdata='0',trap='0')
                cycle+=1;return v
            if is_vector_instruction(ins):
                for event in ('cvx_req','arch_start','uop_alloc','uop_done','cvx_resp'):rows.append(item(event,arch))
                arch+=1
            rows.append(item('retire',order));order+=1
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            path=Path(tmp)/'protocol.csv'
            def write(data):
                with path.open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
            write(rows);valid=validate_trace(path);self.assertGreater(valid['backend_uop_done_count'],0)
            for fault in ('unknown','unmatched','exception'):
                bad=copy.deepcopy(rows)
                if fault=='unknown':bad[0]['event']='bogus'
                elif fault=='unmatched':next(r for r in bad if r['event']=='uop_done')['port']='9'
                else:next(r for r in bad if r['event']=='cvx_resp')['trap']='1'
                write(bad)
                with self.assertRaises(TraceValidationError):validate_trace(path)

    def test_actual_frozen_parent_monitor_before_early_postcheck0_17(self):
        parent,options,testcase,_=self.framework
        import ara_verify.runner as engine
        for code in (0,17):
            with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                out=Path(tmp);root=out/'replay/tests'/NAME;(root/'work').mkdir(parents=True)
                (root/'input.elf').write_bytes(b'Host only')
                opts=replay.worker.build_options(options,self.repo,out,self.ledger)
                abort=threading.Event()
                runner=replay.worker.checked_runner(parent,abort,lambda r:None,lambda n:None)(opts,[],[])
                runner._suite_frozen=True;runner._frozen_binaries[NAME]='Host only hash'
                def monitored(command,cwd,console,timeout,cancel_event=None):
                    Path(console).write_text(c.common.SUCCESS);(Path(cwd)/'run.vcs.log').write_text(c.common.SUCCESS)
                    (root/'commit_trace.csv').write_text('Host only')
                    if code==17:(root/'command.json').write_text('invalid metadata')
                    return(code,1.0,False,False)
                test=testcase(NAME,'app','',Path(self.case['elf']),NAME,TIMEOUT)
                with patch.object(engine,'simulation_image',return_value={}),patch.object(engine,'_run_monitored',monitored),\
                     patch.object(engine,'validate_trace',return_value={}),\
                     patch.object(engine,'check_inputs',side_effect=RuntimeError('actual_parent_early_postcheck')):
                    with replay.worker.engine_hooks(engine,abort,{NAME:root},self.ledger['simv']):
                        with self.assertRaises(RuntimeError if code==0 else ValueError):runner._run_test(test,Path(self.ledger['simv']))
                receipt=c.read(root/'child_outcome.unvalidated.json')
                self.assertEqual(receipt['returncode'],code);self.assertEqual(receipt['source_label'],HISTORICAL)
                self.assertFalse(receipt['architectural_acceptance'])
                self.assertEqual(c.read(out/'first_cause.json')['returncode'],code);self.assertTrue(abort.is_set())

    def test_timeout_negative_preserved_before_metadata(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root=Path(tmp)/NAME;(root/'work').mkdir(parents=True)
            command=replay.worker.monitor_command(root,self.ledger['simv'],NAME)
            (root/'command.json').write_text('invalid metadata')
            abort=threading.Event();wrapped=replay.monitored(lambda *a:(-9,7200.0,True,False),abort,{NAME:root},self.ledger['simv'])
            with self.assertRaises(ValueError):wrapped(command,root/'work',root/'console.log',TIMEOUT)
            self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['returncode'],-9)
            self.assertEqual(c.read(root/'first_cause.json')['kind'],'MONITOR_OUTCOME')

    def test_complete_membership_budget_and_late_abort(self):
        results=[SimpleNamespace(name=NAME,status='PASS',returncode=0,elapsed_s=1.0,reason='')]
        meta=dict(status='COMPLETE',tests=NAMES,status_counts={'PASS':1},completed_at='Host only',jobs=1,
                  timeout_s=TIMEOUT,seed=1,simv=self.ledger['simv'],commit_trace=True,code_coverage=False)
        replay.worker.terminal_gate(results,meta,threading.Event(),self.ledger)
        for bad in ([],results*2):
            with self.assertRaises(ValueError):replay.worker.terminal_gate(bad,meta,threading.Event(),self.ledger)
        abort=threading.Event();abort.set()
        with self.assertRaises(ValueError):replay.worker.terminal_gate(results,meta,abort,self.ledger)
        self.assertEqual((JOBS,TIMEOUT,OUTER),(1,7200,9000))
        with self.assertRaises(ValueError):replay.authorization_gate('0'*64,None,None)
        c.common.resource_math([],32*1024**3,HERE,1,0)
        with self.assertRaises(ValueError):c.common.resource_math([],31*1024**3,HERE,1,0)

    def test_source_binding_independent_model_and_pins(self):
        from model import compare
        self.assertEqual(compare(0,0,0x8000),(1,0));self.assertEqual(compare(0,0x7c55,0x7e55),(0,16))
        pins=replay.reference_inputs();self.assertEqual(pins[str(READY)],READY_SHA)
        accepted=replay.independent_reference()
        self.assertEqual(accepted[str(replay.BINDING)],c.sha(replay.BINDING))
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            f=Path(tmp)/'pin';f.write_text('original');pins={str(f):c.sha(f)};f.write_text('drift')
            with self.assertRaises(ValueError):c.common.base.verify_pins(pins)


if __name__=='__main__':
    started=time.monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Gates))
    pins={str(HERE/f):c.sha(HERE/f) for f in ('newscope.py','model.py','elf.py','dut_strict.py','checker.py','replay.py','test_host.py')}
    replay.durable(HERE/replay.HOST_REPORT,dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),elapsed_s=time.monotonic()-started,pins=pins,
        source_data_positives=2,source_mutations=19,unused_helper_PC_negatives=174,normal_events=6,
        actual_frozen_parent_postcheck_codes=[0,17],timeout_negative_code=-9,DUT_started=False,reference_started=False))
    raise SystemExit(not result.wasSuccessful())
