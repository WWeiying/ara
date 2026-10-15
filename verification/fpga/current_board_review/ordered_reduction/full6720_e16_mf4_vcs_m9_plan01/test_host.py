"""Small actual-SoC RVFI/source/owner witnesses, not a new reference run."""
import tempfile
import threading
from types import SimpleNamespace
import unittest
from scope import *
from specification import *
from strict import Strict
import checker
import replay
def raw(c,pc,rd=0,value=0,address=0,rm=0,wm=0,wd=0):
    return dict(cycle=str(c.retired),event='retire',order=str(c.retired),port='0',trans_id='-1',pc=f'{pc:016x}',insn=c.code[pc]['insn'].zfill(8),rd=str(rd),rd_wdata=f'{value:016x}',mem_addr=f'{address:016x}',mem_rmask=f'{rm:02x}',mem_wmask=f'{wm:02x}',mem_wdata=f'{wd:016x}',trap='0')
def ready(n=3090):
    c=Strict();c.calls=n;c.cap=3;c.pre=6;c.fresh=18;g=c.g()
    c.counts.update(input_SH=16*(g['scenario']+1),seed_SD=16*(g['scenario']+1),mask_SD=8*(g['row']+1),fixture_fields=2*(g['row']+1))
    c.csr.update(frm=0,fflags=0,vstart=0)
    for name,vs,w in [('input',[source.original_input(c.s['bits'],g['scenario'],j) for j in range(16)]+[0]*496,2),('seed',[g['seed']]*64,2),('mask',[g['mask']]*64,1),('output',[91]*144,1)]:
        for j,v in enumerate(vs):c.memory.update({c.a[name]+j*w+k:(v>>(8*k))&255 for k in range(w)})
    c.regs.update(dict(zip(range(10,18),[c.a['input'],c.a['seed'],c.a['output']+8,g['vl'],16,c.a['mask'],g['rm'],g['sticky']])))
    c.regs[1]=next(iter(c.soc_reads));c.regs[8]=c.a['output'];c.nextpc=c.helpers[g['op']][0]['pc']
    return c
def helper_row(c,i):
    g=c.g();rd=val=0
    if i in (0,3,6,18):rd,val=5,64 if i in (0,18) else 16 if i==3 else g['vl']
    if i in (7,8):rd=29 if i==7 else 30
    if i in (12,13,14,15):rd,val=(10 if i in (12,15) else 6),(0 if i==12 else g['flags'] if i==13 else g['flags']<<32)
    return raw(c,c.helpers[g['op']][i]['pc'],rd,val)
def run_helper(c):
    for i in range(21):c.consume(helper_row(c,i))
def output_row(c,i,flip=0,rm=255):
    pc=next(p-14 for p,j in c.readmap.items() if j==i);d=isa.memory_desc(int(c.code[pc]['insn'],16));c.nextpc=pc
    c.regs[d['base']]=c.a['output'];b=c.result_bytes(c.g());v=int.from_bytes(b[8*i:8*i+8],'little')^flip
    return raw(c,pc,d['register'],v,c.a['output']+8*i,rm)
class Tests(unittest.TestCase):
    def test_actual_soc_spec(self):
        s=specification();self.assertNotIn('tohost',s['symbols']);self.assertNotIn('replay_log',s['symbols'])
        self.assertEqual(sum(map(len,s['helpers']))+len(s['capacity']),66)
        self.assertEqual(owner_contract(),dict(memory=33600,target_required=5760,target_elidable=960))
        self.assertEqual(read_json_roundtrip(s),s)
    def test_three_ops_zero_nonzero_last(self):
        for n in (0,1,2,3,4,5,120,122,124,3090,3091,6719):
            c=ready(n);run_helper(c)
            for i in range(18):c.consume(output_row(c,i))
            self.assertEqual(c.calls,n+1);self.assertEqual(c.reads,0)
    def test_wrong_NV_vstart_restore(self):
        for i in (12,13,17):
            c=ready()
            for j in range(i):c.consume(helper_row(c,j))
            r=helper_row(c,i)
            if i==17:c.regs[30]=16
            else:r['rd_wdata']='1' if i==12 else '0'
            with self.assertRaises(ValueError):c.consume(r)
    def test_short_BE_wrong_value_tail_guard(self):
        for i,flip in ((0,1),(1,1),(16,1),(17,1)):
            c=ready();run_helper(c)
            for j in range(i):c.consume(output_row(c,j))
            with self.assertRaisesRegex(ValueError,'all144B'):c.consume(output_row(c,i,flip))
        c=ready();run_helper(c)
        with self.assertRaisesRegex(ValueError,'BE'):c.consume(output_row(c,0,rm=15))
    def test_missing_helper_wrong_code(self):
        c=ready();c.consume(helper_row(c,0))
        with self.assertRaisesRegex(ValueError,'control flow'):c.consume(helper_row(c,2))
        c=ready();r=helper_row(c,0);r['insn']='00000013'
        with self.assertRaisesRegex(ValueError,'PC/code'):c.consume(r)
    def test_missing_output_fresh_upper_seed_mask(self):
        for name,offset in [('seed',127),('mask',63),('input',1023),('output',143)]:
            c=ready();c.memory[c.a[name]+offset]^=1
            with self.assertRaisesRegex(ValueError,'initialized'):c.consume(helper_row(c,0))
        c=ready();c.fresh=17
        with self.assertRaisesRegex(ValueError,'setup'):c.consume(helper_row(c,0))
    def test_wrong_fixture_bank(self):
        c=ready();c.fresh=0;c.counts['fixture_fields']=3090
        pc=0x80000330;c.nextpc=pc;c.regs[15]=c.a['fixtures']+1545*16
        v=isa.word(c.memory,c.regs[15],8)
        with self.assertRaisesRegex(ValueError,'bank1'):c.consume(raw(c,pc,14,v,c.regs[15],255))
    def test_exact_scenario_not_percall_input(self):
        c=ready();c.active=None;c.calls=1;c.nextpc=0x80000238;c.regs[28]=c.a['input'];c.regs[15]=0
        with self.assertRaisesRegex(ValueError,'scenario-only'):c.consume(raw(c,c.nextpc,address=c.a['input'],wm=3))
    def test_owner_deletion_alloff_and_VL0(self):
        for op,i,vl,required in [(0,1,0,True),(1,5,0,True),(2,19,0,True),(0,11,0,False),(1,11,1,True),(2,11,16,True)]:
            s=specification();kind,need=helper_owner(s,op,i,dict(vl=vl,mask=0));self.assertEqual(need,required)
            ins=int(s['helpers'][op][i]['insn'],16);o=checker.Owners(SimpleNamespace(is_vector_instruction=lambda _:True));o.retvec=o.arch=[ins]
            ledger=[dict(insn=ins,required=need,kind=kind,call=0,helper_index=i)]
            if required:
                with self.assertRaisesRegex(ValueError,'necessary owner'):o.coverage(ledger)
            else:o.coverage(ledger)
            o.alloc[0]=o.done[0]=1;o.coverage(ledger)
    def test_owner_mismatch(self):
        o=checker.Owners(SimpleNamespace(is_vector_instruction=lambda _:True));o.retvec=o.arch=[0x0205d807];o.alloc[0]=1
        with self.assertRaisesRegex(ValueError,'balance'):o.coverage([dict(insn=o.arch[0],required=True,kind='memory')])
    def test_opaque_spill_exact_nonzero(self):
        c=Strict();pc=c.s['opaque'][0];d=isa.memory_desc(int(c.code[pc]['insn'],16));c.nextpc=pc;c.regs[2]=c.a['__stack_top']-384
        addr=c.regs[2]+d['offset'];c.consume(raw(c,pc,address=addr,wm=255,wd=0x12345678))
        self.assertEqual(isa.word(c.memory,addr,8),0x12345678);c.nextpc=pc
        with self.assertRaisesRegex(ValueError,'ABI spill'):c.consume(raw(c,pc,address=addr,wm=255))
    def test_no_partial_acceptance(self):
        with self.assertRaisesRegex(ValueError,'EOF'):ready().finish()
    def test_detail_console_and_wrong_count(self):
        text='BOARD_CASE_BEGIN '+NAME+'\n'+MARKER+'\nBOARD_CASE_PASS '+NAME+'\nBOARD_REPLAY_PASS\n'+checker.common.SUCCESS+'\n$finish\n'
        checker.console_gate(text)
        with self.assertRaises(ValueError):checker.console_gate(text.replace('cases=6720','cases=1'))
        self.assertIsNotNone(checker.VETO.search('RVV_FP_REDSPECIAL_DETAIL scenario='))
    def test_numeric_before_postcheck_and_abort(self):
        for code in (0,17):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);(root/'work').mkdir();cmd=replay.base.monitor_command(root,'/not-executed/simv',NAME)
                replay.durable(root/'command.json',dict(command=cmd,cwd=str(root/'work')));abort=threading.Event()
                f=replay.base.monitored(lambda *args:(code,1.0,False,False),abort,{NAME:root},'/not-executed/simv')
                f(cmd,root/'work',root/'console.log',TIMEOUT)
                try:raise ValueError('postchecker failure')
                except ValueError:pass
                self.assertEqual(read(root/'child_outcome.unvalidated.json')['returncode'],code);self.assertEqual(abort.is_set(),code!=0)
    def test_command_seed_and_plan_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cmd=replay.base.monitor_command(root,'/simv',NAME);cmd[3]='+ntb_random_seed=2'
            f=replay.base.monitored(lambda *args:self.fail('Must reject before child'),threading.Event(),{NAME:root},'/simv')
            with self.assertRaisesRegex(ValueError,'Exact monitor'):f(cmd,root/'work',root/'console.log',TIMEOUT)
            replay.durable(root/'plan.json',dict(wrong=True))
            with self.assertRaisesRegex(ValueError,'plan drift'):replay.disk_gate(root,'0'*64)
def read_json_roundtrip(s):return json.loads(json.dumps(s))
if __name__=='__main__':unittest.main()
