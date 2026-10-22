"""Bounded synthetic Host counterexamples, not reference or DUT execution."""
import copy
import tempfile
import threading
import unittest
from scope import *
import checker
import replay
from specification import specification,model,helper_owner
from strict import Strict,word

def rawrow(c,pc,rd=0,value=0,address=0,rmask=0,wmask=0,wdata=0):
    return dict(cycle=str(c.retired),event='retire',order=str(c.retired),port='0',trans_id='-1',
        pc=f'{pc:016x}',insn=c.code[pc]['insn'].zfill(8),rd=str(rd),rd_wdata=f'{value:016x}',
        mem_addr=f'{address:016x}',mem_rmask=f'{rmask:02x}',mem_wmask=f'{wmask:02x}',
        mem_wdata=f'{wdata:016x}',trap='0')

def ready(ordinal=0):
    c=Strict();c.calls=ordinal;c.cap=3;c.pre=6;c.bss=c.s['BSS_bytes']//8
    for p in range(c.a['__bss_start'],c.a['__bss_end']): c.memory[p]=0
    g=c.current();c.record_index=g['record_index'];c.record_loads=g['record_index']+1
    for i,(address,value,width) in enumerate(c.expected_setup(g)):
        if 16<=i<24:
            j=i-16;rec=word(c.memory,c.a['oracle_records']+8*g['record_index'],8)
            row=(rec>>(48 if j%2==0 else 56))&255;addr=c.a['input_periods']+32*row+8*(j//2)
            c.input_load(c.s['input_loads'][j]['pc'],addr,word(c.memory,addr,8),8)
        c.setup_store(c.s['stores'][i]['pc'],address,value,width)
        for j in range(width): c.memory[address+j]=(value>>(8*j))&255
    c.regs.update(dict(zip(range(10,18),[c.a['a'],c.a['b'],c.a['output']+1,g['vl'],16,c.a['mask'],0,g['sticky']])))
    c.regs.update({22:word(c.memory,c.a['oracle_records']+8*g['record_index'],8),23:g['sticky'],1:c.s['output_read'],8:c.a['output']})
    c.nextpc=c.s['helpers'][g['op']][0]['pc']
    return c

def helper_row(c,i):
    g=c.current();op=g['op'];d=2 if op>=4 else 0;pc=c.s['helpers'][op][i]['pc']
    rd=val=addr=rm=0
    if i==0: rd,val=30,0
    if i in (1,6+d,14+d): rd,val=5,g['vl'] if i==6+d else 16
    if op>=4 and i==6: rd,val,addr=7,g['b'][0],c.a['b'];rm=3<<(addr%8)
    if op>=4 and i==7: rd,val=0,g['b'][0]
    if i==9+d: rd,val=10,0
    if i==10+d: rd,val=6,g['flags']
    if i==11+d: rd,val=6,g['flags']<<32
    if i==12+d: rd,val=10,g['flags']<<32
    return rawrow(c,pc,rd,val,addr,rm)

def run_helper(c):
    for i in range(len(c.s['helpers'][c.current()['op']])): c.consume(helper_row(c,i))

def output_value(c,maximum=False):
    f=max if maximum else min
    return 91|(sum(f(v)<<i for i,v in enumerate(c.current()['allowed']))<<8)|(91<<24)

class Tests(unittest.TestCase):
    def test_actual_soc_spec_not_spike(self):
        s=specification();self.assertEqual(s['elf_sha256'],ELF_SHA)
        self.assertNotIn('tohost',s['symbols']);self.assertNotIn('replay_log',s['symbols'])
        self.assertEqual(sum(map(len,s['helpers']))+len(s['capacity']),185)
        self.assertEqual(replay.owner_contract(),dict(memory=89600,target_required=15360,target_elidable=2560))
    def test_all10_windows_zero_nonzero_last_seed(self):
        for seed in (0,1,16,31):
            for op in range(10):
                c=ready(seed*560+op*56+48);run_helper(c)
                val=output_value(c)
                c.consume(rawrow(c,c.s['output_read'],8,val,c.a['output'],15))
                self.assertEqual(c.calls,seed*560+op*56+49)
                self.assertEqual(c.regs[0],0)
    def scalar(self,seed=1):
        c=ready(seed*560+4*56+48)
        for i in range(7): c.consume(helper_row(c,i))
        return c
    def test_fpr_all32seed_payload_and_x0(self):
        for seed in range(32):
            c=self.scalar(seed);c.consume(helper_row(c,7))
            self.assertEqual(c.fp[0],c.current()['b'][0]);self.assertEqual(c.regs[0],0)
            self.assertEqual(c.raw_scalar_seeds[seed],1)
    def test_fpr_wrong_rd(self):
        c=self.scalar();r=helper_row(c,7);r['rd']='7'
        with self.assertRaisesRegex(ValueError,'FPR committed'):c.consume(r)
    def test_fpr_nonzero_zero_box_highbits(self):
        for val in (0,0xffffffffffff8000,0x100008000):
            c=self.scalar();r=helper_row(c,7);r['rd_wdata']=f'{val:x}'
            with self.assertRaisesRegex(ValueError,'FPR committed'):c.consume(r)
    def test_fpr_zero_seed_nonzero(self):
        c=self.scalar(0);r=helper_row(c,7);r['rd_wdata']='1'
        with self.assertRaisesRegex(ValueError,'FPR committed'):c.consume(r)
    def test_fpr_wrong_t2(self):
        c=self.scalar();c.regs[7]=0
        with self.assertRaisesRegex(ValueError,'t2 source'):c.consume(helper_row(c,7))
    def test_missing_fmv(self):
        c=self.scalar()
        with self.assertRaisesRegex(ValueError,'control flow'):c.consume(helper_row(c,8))
    def test_bad_opcode(self):
        c=self.scalar();r=helper_row(c,7);r['insn']='f2000053'
        with self.assertRaisesRegex(ValueError,'PC/code'):c.consume(r)
    def test_deleted_fresh_and_input_ld(self):
        for attr,value in [('fresh',40),('input_reads',7)]:
            c=ready();setattr(c,attr,value)
            with self.assertRaisesRegex(ValueError,'fresh setup'):c.consume(helper_row(c,0))
    def test_full_array_mask_upper_and_output_tail(self):
        for name,offset in [('mask',127),('output',129),('a',31),('b',31)]:
            c=ready();c.memory[c.a[name]+offset]^=1
            with self.assertRaisesRegex(ValueError,'initialized'):c.consume(helper_row(c,0))
    def test_wrong_record_and_input(self):
        c=ready();c.record_index+=1
        with self.assertRaisesRegex(ValueError,'fresh setup'):c.consume(helper_row(c,0))
        c=ready();c.fresh=16;c.input_reads=0
        with self.assertRaisesRegex(ValueError,'period'):c.input_load(c.s['input_loads'][0]['pc'],c.a['input_periods']+7,0,8)
    def test_original_active_guard_vl0_errors(self):
        for ordinal,flip in [(48,1<<8),(0,1<<8),(48,1),(48,1<<24),(48,1|(1<<24))]:
            c=ready(ordinal);run_helper(c)
            with self.assertRaises(ValueError):c.consume(rawrow(c,c.s['output_read'],8,output_value(c)^flip,c.a['output'],15))
    def test_tail_allowed_not_strengthened(self):
        c=ready(8);run_helper(c)
        c.consume(rawrow(c,c.s['output_read'],8,output_value(c,True),c.a['output'],15))
        self.assertEqual(c.calls,9)
    def test_nv_sticky_vstart_restore(self):
        n=next(i for i,g in enumerate(model()) if g['flags']&16)
        for index,value in [(9,1),(10,0),(13,None)]:
            c=ready(n);d=2 if c.current()['op']>=4 else 0
            for i in range(index+d): c.consume(helper_row(c,i))
            r=helper_row(c,index+d)
            if value is None:c.regs[30]=16
            else:r['rd_wdata']=str(value)
            with self.assertRaises(ValueError):c.consume(r)
    def test_short_lwu_be(self):
        c=ready();run_helper(c)
        with self.assertRaisesRegex(ValueError,'BE'):c.consume(rawrow(c,c.s['output_read'],8,output_value(c),c.a['output'],3))
    def test_uninitialized_read_and_wrong_address(self):
        c=self.scalar();r=helper_row(c,7);r['mem_rmask']='1'
        with self.assertRaisesRegex(ValueError,'Nonmemory'):c.consume(r)
    def test_partial_eof(self):
        with self.assertRaisesRegex(ValueError,'EOF'):ready().finish()
    def test_bss_nonzero_and_outside(self):
        for wrong in ('value','address'):
            c=Strict();c.pre=5;c.nextpc=c.s['bss_store'];c.regs[5]=c.a['__bss_start']
            address=c.regs[5];wd=0
            if wrong=='value':wd=1
            else:address+=8;c.regs[5]=address
            with self.assertRaises(ValueError):c.consume(rawrow(c,c.s['bss_store'],address=address,wmask=255,wdata=wd))
    def test_opaque_spill_not_unknown_zero(self):
        c=Strict();pc=c.s['opaque_initial_spills'][0];d=__import__('specification').source.memory_desc(int(c.code[pc]['insn'],16))
        c.nextpc=pc;c.regs[2]=c.a['__stack_top']-240
        addr=c.regs[2]+d['offset'];c.consume(rawrow(c,pc,address=addr,wmask=255,wdata=0x12345678))
        self.assertEqual(word(c.memory,addr,8),0x12345678)
        c.nextpc=pc
        with self.assertRaisesRegex(ValueError,'ABI spill'):c.consume(rawrow(c,pc,address=addr,wmask=255,wdata=0))
    def test_owner_deletion_vl0_memory_and_nonempty_target(self):
        from types import SimpleNamespace
        for op,i,vl,required in [(0,2,0,True),(4,17,0,True),(0,8,0,False),(4,10,1,True)]:
            s=specification();g=dict(vl=vl);kind,need=helper_owner(s,op,i,g);self.assertEqual(need,required)
            ins=int(s['helpers'][op][i]['insn'],16)
            o=checker.Owners(SimpleNamespace(is_vector_instruction=lambda x:True));o.retvec=[ins];o.arch=[ins]
            ledger=[dict(insn=ins,required=need,kind=kind,call=0,helper_index=i)]
            if required:
                with self.assertRaisesRegex(ValueError,'necessary owner'):o.coverage(ledger)
            else:self.assertEqual(len(o.coverage(ledger)[0]),1)
            o.alloc[0]=o.done[0]=1;self.assertEqual(len(o.coverage(ledger)[0]),1)
    def test_owner_alloc_done_mismatch(self):
        from types import SimpleNamespace
        o=checker.Owners(SimpleNamespace(is_vector_instruction=lambda x:True));o.retvec=o.arch=[0x02055407];o.alloc[0]=1
        with self.assertRaisesRegex(ValueError,'balance'):o.coverage([dict(insn=o.arch[0],required=True,kind='memory')])
    def test_detail_immediate_and_wrong_marker(self):
        self.assertIsNotNone(checker.VETO.search('RVV_FP_COMPARE_DETAIL op=4'))
        text='BOARD_CASE_BEGIN '+NAME+'\n'+MARKER+'\nBOARD_CASE_PASS '+NAME+'\nBOARD_REPLAY_PASS\n'+checker.common.SUCCESS+'\n$finish\n'
        checker.console_gate(text)
        with self.assertRaises(ValueError):checker.console_gate(text.replace('cases=17920','cases=265'))
    def test_durable_child_before_checkerthrow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'work').mkdir();simv='/not-executed/simv'
            cmd=replay.monitor_command(root,simv,NAME)
            replay.durable(root/'command.json',dict(command=cmd,cwd=str(root/'work')))
            abort=threading.Event();f=replay.monitored(lambda *a:(0,1.0,False,False),abort,{NAME:root},simv)
            f(cmd,root/'work',root/'console.log',TIMEOUT)
            try:raise ValueError('intentional postchecker throw')
            except ValueError:pass
            self.assertEqual(read(root/'child_outcome.unvalidated.json')['returncode'],0)
            self.assertFalse(read(root/'child_outcome.unvalidated.json')['architectural_acceptance'])
    def test_metadata_seed_preload_cwd_rejected(self):
        for which in ('seed','preload','cwd'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'work').mkdir();cmd=replay.monitor_command(root,'/simv',NAME)
                if which=='seed':cmd[3]='+ntb_random_seed=2'
                if which=='preload':cmd[4]='+PRELOAD=/wrong.elf'
                f=replay.monitored(lambda *a: self.fail('Must reject before monitor'),threading.Event(),{NAME:root},'/simv')
                with self.assertRaisesRegex(ValueError,'Exact monitor'):f(cmd,root/('wrong' if which=='cwd' else 'work'),root/'console.log',TIMEOUT)
    def test_numeric_nonzero_latched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'work').mkdir();cmd=replay.monitor_command(root,'/simv',NAME)
            replay.durable(root/'command.json',dict(command=cmd,cwd=str(root/'work')))
            abort=threading.Event();f=replay.monitored(lambda *a:(17,1.0,False,False),abort,{NAME:root},'/simv')
            f(cmd,root/'work',root/'console.log',TIMEOUT);self.assertTrue(abort.is_set())
            self.assertEqual(read(root/'child_outcome.unvalidated.json')['returncode'],17)
    def test_plan_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);replay.durable(out/'plan.json',dict(changed=True))
            with self.assertRaisesRegex(ValueError,'plan drift'):replay.disk_gate(out,'0'*64)
    def test_host_mutable_state_independent(self):
        a,b=ready(),ready();a.regs[7]=1;a.console.append(65);a.counts['extra']=1
        self.assertNotIn(7,b.regs);self.assertEqual(b.console,bytearray());self.assertNotIn('extra',b.counts)

def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    replay.durable(HERE/'host02.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST_ONLY_NOT_DUT',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),pins=replay.owned_pins(),
        actual_DUT_execution=False,full_reference_rerun=False))
    return int(not result.wasSuccessful())
if __name__=='__main__':raise SystemExit(main())
