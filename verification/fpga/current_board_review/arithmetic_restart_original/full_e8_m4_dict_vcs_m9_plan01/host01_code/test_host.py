"""Actual ELF ABI and full source constructed rows; no DUT or reference reads."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
import checker as c
import replay as r
from host_records import Builder

class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=c.specification();cls.gold=c.model();cls.reset=c.Strict(cls.spec)
        c.common.image_context(r.IMAGE);cls.protocol=sys.modules['ara_verify.trace']
        builder=Builder(cls.spec);cls.abi=list(builder.abi())
        cls.before_abi_store=deepcopy(cls.reset)
        for row in cls.abi[:-2]:cls.before_abi_store.consume(row)
        state=c.Strict(cls.spec);observer=c.OwnerObserver(cls.protocol)
        cls.snapshots={};builder=Builder(cls.spec)
        for row in builder.protocol_rows(builder.records()):
            pc=int(row['pc'],16)
            if row['event']=='retire':
                site=state.lookup.get(pc)
                if site and site[0]=='op_0' and site[1]==0 and not state.calls:cls.snapshots['entry']=(deepcopy(state),dict(row))
                if site and site[0]=='op_0' and site[1]==9 and len(state.calls)==1:cls.snapshots['vstart']=(deepcopy(state),dict(row))
                if int(row['mem_rmask'],16) and state.active:
                    offset=int(row['mem_addr'],16)-state.s['out']
                    if offset in (0,512) and state.active['ordinal']==0:cls.snapshots['word'+str(offset)]=(deepcopy(state),dict(row))
                    if state.active['vl'] and state.active['vstart']<state.active['vl'] and offset==0 and 'active_word' not in cls.snapshots:
                        cls.snapshots['active_word']=(deepcopy(state),dict(row))
                if pc==state.spec['exit_store']:cls.snapshots['exit']=(deepcopy(state),dict(row))
            observer.observe(row);state.consume(row)
        cls.state=state;cls.observer=observer
        cls.strict=state.finish();cls.generic=observer.finish()
        cls.coverage=observer.owner_coverage(state.offloads,dict(rows=state.gold,masks=[state.gold[i]['mask'] for i in (0,3,6)]))

    def test_full4095_complete_data(self):
        self.assertEqual([self.strict[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads')],
            [4095,2096640,8190,4095,53235,266175])
        self.assertEqual(self.strict['routine_counts'],[4095]*13)
        self.assertEqual({x['op'] for x in self.strict['call_ledger']},set(range(25)))
        self.assertEqual((self.generic['rows'],self.generic['retire_count']), (self.strict['rows'],self.strict['retired']))
        self.assertEqual((self.coverage['compulsory_memory_owners'],self.coverage['required_target_owners']), (20475,2610))

    def test_actual_elf_abi(self):
        state=deepcopy(self.reset)
        for row in self.abi:state.consume(row)
        self.assertEqual(state.value(0x800fffe8,8),0x8000004e)
        self.assertEqual(state.bss_next,state.s['__bss_end'])
        self.assertTrue(state.main_entered and state.body_entered)
        self.assertEqual(state.csr_count,5)

    def test_actual_abi_unknown_ra(self):
        state=deepcopy(self.before_abi_store);del state.regs[1]
        with self.assertRaisesRegex(ValueError,'source GPR'):state.consume(self.abi[-2])
        self.assertNotIn(1,state.regs)

    def test_actual_abi_wrong_be_or_data(self):
        for key,value in (('mem_wmask','0f'),('mem_addr','00000000800fffe0'),('mem_wdata','0000000000000001')):
            with self.subTest(key=key),self.assertRaises(ValueError):deepcopy(self.before_abi_store).consume(dict(self.abi[-2],**{key:value}))

    def test_deleted_fresh_init(self):
        state,row=self.snapshots['entry'];state=deepcopy(state);state.fresh['out']-=set(range(80,88))
        with self.assertRaisesRegex(ValueError,'Deleted fresh'):state.consume(row)

    def test_seed_and_mask_complete_original_inputs(self):
        for name in ('a','b','mask'):
            state,row=self.snapshots['entry'];state=deepcopy(state);state.memory[state.s[name]+1]^=1
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'initialized values'):state.consume(row)

    def test_word_every_byte_and_guards(self):
        for key in ('word0','word512','active_word'):
            state,row=self.snapshots[key];size=c.memory_op(int(row['insn'],16))['size']
            for byte in range(size):
                with self.subTest(key=key,byte=byte),self.assertRaisesRegex(ValueError,'expected='):
                    deepcopy(state).consume(dict(row,rd_wdata=f'{int(row["rd_wdata"],16)^(1<<(8*byte)):016x}'))

    def test_tail_two_bytes_and_missing_read(self):
        state,row=self.snapshots['word512']
        with self.assertRaises(ValueError):deepcopy(state).consume(dict(row,mem_rmask='ff'))
        with self.assertRaises(ValueError):deepcopy(state).finish_call()
        state=deepcopy(self.state);state.calls[-1]['reads'].remove(64)
        with self.assertRaises(ValueError):state.finish()

    def test_vstart_and_true_failure_pc(self):
        state,row=self.snapshots['vstart']
        with self.assertRaisesRegex(ValueError,'returned vstart'):deepcopy(state).consume(dict(row,rd_wdata='0000000000000001'))
        state,row=self.snapshots['entry'];pc=state.spec['failure_pcs'][0]
        with self.assertRaisesRegex(ValueError,'failure/trap'):deepcopy(state).consume(dict(row,pc=f'{pc:016x}',insn=f'{state.code[pc]:08x}'))

    def test_required_active_target_and_op24_pair_deleted(self):
        for op in (0,24):
            index=next(i for i,r0 in enumerate(self.state.offloads) if r0['kind']=='target' and r0['required'] and self.gold[r0['call']]['op']==op)
            seq=self.coverage['owner_ledger'][index]['arch_order']
            observer=deepcopy(self.observer);self.assertGreater(observer.owner_alloc[seq],0)
            observer.owner_alloc[seq]=observer.owner_done[seq]=0
            with self.subTest(op=op),self.assertRaisesRegex(ValueError,'necessary architectural owner'):
                observer.owner_coverage(self.state.offloads,dict(rows=self.gold,masks=[self.gold[i]['mask'] for i in (0,3,6)]))
        self.assertEqual(sum(g['op']==24 and g['vstart']<g['vl'] for g in self.gold),117)

    def test_generic_drop_arch_or_uop(self):
        observer=deepcopy(self.observer);observer.arch.pop()
        with self.assertRaises((ValueError,AssertionError)):observer.finish()
        observer=deepcopy(self.observer);observer.uops[0]=(0,0)
        with self.assertRaises((ValueError,AssertionError)):observer.finish()

    def test_empty_target_qualification(self):
        self.assertEqual(sum(not x['required'] for x in self.state.offloads if x['kind']=='target'),1485)
        self.assertEqual(sum(x['required'] for x in self.state.offloads if x['kind']=='memory'),20475)

    def test_wrong_exit(self):
        state,row=self.snapshots['exit']
        with self.assertRaises(ValueError):deepcopy(state).consume(dict(row,mem_wdata='0000000000000001'))

    def test_console_actual_markers_and_fail_veto(self):
        c.console_gate(c.marker()+'\n',simulator=False)
        c.console_gate(c.marker()+'\n'+c.common.SUCCESS+'\n$finish\n')
        for text in (c.marker()+'\nFAIL\n',c.marker()+'\n'+c.marker()+'\n',c.marker()+'\n'):
            with self.assertRaises(ValueError):c.console_gate(text)

    def test_numeric_first_0_17_timeout_and_first_record(self):
        for rc,timed in ((0,False),(17,False),(-9,True)):
            with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
                root=Path(tmp);abort=threading.Event();r.durable(root/'command.json',dict(command=['host']))
                monitor=r.monitored_with_outcome(lambda *args:(rc,0.01,timed,False),abort)
                monitor(['host'],root,root/'console.log',10800)
                self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['returncode'],rc)
                with self.assertRaises(FileExistsError):monitor(['host'],root,root/'console.log',10800)
                self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['returncode'],rc)

    def test_lateabort_postcheck_notpass(self):
        for throws in (False,True):
            abort=threading.Event();result=SimpleNamespace(status='PASS',returncode=0,reason='')
            class Parent:
                def __init__(self):pass
                def _run_test(self,*args):return result
            def check(_):
                abort.set()
                if throws:raise ValueError('postcheck firstcause')
            got=r.checked_runner(Parent,abort,check,lambda _:None)()._run_test(SimpleNamespace(name=c.ID),None)
            self.assertNotEqual(got.status,'PASS');self.assertEqual(got.returncode,0)

    def test_fixed_bound_review_and_lateplan(self):
        self.assertEqual((r.JOBS,r.CASE_BOUND,r.WORKER_BOUND,r.OUTER),(1,10800,12000,13200))
        with self.assertRaises(ValueError):r.reviews({'pins':{}},'x',None,None,None,None)
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            root=Path(tmp);r.durable(root/'plan.json',{})
            with self.assertRaises(ValueError):r.terminal_disk_gate(root,'wrong',r.IMAGE)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    pins={str(c.HERE/name):c.sha(c.HERE/name) for name in ('checker.py','replay.py','test_host.py','host_records.py','reset_profile.json')}
    r.durable(c.HERE/'host01.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',tests=result.testsRun,
        failures=len(result.errors)+len(result.failures),pins=pins,actual_abi_entry_checked=result.wasSuccessful(),full4095_streams=1,
        full_positive_shapes=[c.SHAPE] if result.wasSuccessful() else [],CSV_reads=0,DUT_reference_build_runs=0,
        fixture='Constructed source/actual-machine-site rows, not captured DUT or a scalar ISA emulator'))
    raise SystemExit(not result.wasSuccessful())
