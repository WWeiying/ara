"""Actual ELF ABI and full source constructed rows; no DUT or reference reads."""
from copy import deepcopy as standard_deepcopy, copy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
import time
import checker as c
import replay as r
from host_records import Builder

def deepcopy(value):
    if isinstance(value,c.Strict):
        result=copy(value)
        result.regs=value.regs.copy();result.memory=value.memory.copy()
        result.calls=[dict(call,reads=set(call['reads'])) for call in value.calls]
        result.active=result.calls[value.active['ordinal']] if value.active is not None else None
        result.offloads=[dict(offload) for offload in value.offloads]
        result.fresh={name:set(bits) for name,bits in value.fresh.items()}
        result.counts=list(value.counts);result.console=bytearray(value.console)
        return result
    if isinstance(value,c.OwnerObserver):
        result=copy(value)
        for name in ('count','pcs','pending','uops','owner_alloc','owner_done'):
            setattr(result,name,getattr(value,name).copy())
        for name in ('requests','arch','retvec'):setattr(result,name,list(getattr(value,name)))
        result.before=value.before.copy();result.after=value.after.copy()
        return result
    return standard_deepcopy(value)

class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start=time.monotonic();print('PHASE spec/model/ABI START',flush=True)
        cls.spec=c.specification();cls.gold=c.model();cls.reset=c.Strict(cls.spec)
        c.common.image_context(r.IMAGE);cls.protocol=sys.modules['ara_verify.trace']
        builder=Builder(cls.spec);cls.abi=list(builder.abi())
        cls.before_abi_store=deepcopy(cls.reset)
        for row in cls.abi[:-2]:cls.before_abi_store.consume(row)
        state=c.Strict(cls.spec);observer=c.OwnerObserver(cls.protocol)
        cls.snapshots={};builder=Builder(cls.spec)
        class HostRows:
            fieldnames=c.mature.transport.transport.FIELDS
            def __iter__(self):return iter(builder.protocol_rows(builder.records()))
        print(f'PHASE full4095 transport START elapsed={time.monotonic()-start:.3f}s',flush=True)
        for row in observer.rows(HostRows()):
            pc=int(row['pc'],16)
            if row['event']=='retire':
                site=state.lookup.get(pc)
                if site and site[0]=='op_0' and site[1]==0 and not state.calls:cls.snapshots['entry']=(deepcopy(state),dict(row))
                if site and site[0]=='op_0' and site[1]==9 and len(state.calls)==1:cls.snapshots['vstart']=(deepcopy(state),dict(row))
                if int(row['mem_rmask'],16) and state.active:
                    offset=int(row['mem_addr'],16)-state.s['out']
                    if offset in (0,64) and state.active['ordinal']==0:cls.snapshots['word'+str(offset)]=(deepcopy(state),dict(row))
                    if state.active['vl'] and state.active['vstart']<state.active['vl'] and offset==0 and 'active_word' not in cls.snapshots:
                        cls.snapshots['active_word']=(deepcopy(state),dict(row))
                if pc==state.spec['exit_store']:cls.snapshots['exit']=(deepcopy(state),dict(row))
            state.consume(row)
            if state.rows%200000==0:print(f'PHASE stream rows={state.rows} calls={len(state.calls)} elapsed={time.monotonic()-start:.3f}s',flush=True)
        print(f'PHASE stream COMPLETE rows={state.rows} elapsed={time.monotonic()-start:.3f}s',flush=True)
        cls.state=state;cls.observer=observer
        cls.strict=state.finish();cls.generic=observer.finish()
        cls.coverage=observer.owner_coverage(state.offloads,dict(rows=state.gold,masks=[state.gold[i]['mask'] for i in (0,3,6)]))

    def test_full4095_complete_data(self):
        self.assertEqual([self.strict[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads')],
            [4095,131040,8190,4095,53235,36855])
        self.assertEqual(self.strict['routine_counts'],[4095]*13)
        self.assertEqual({x['op'] for x in self.strict['call_ledger']},set(range(25)))
        self.assertEqual((self.generic['rows'],self.generic['retire_count']), (self.strict['rows'],self.strict['retired']))
        contract=c.owner_contract()
        self.assertEqual((self.coverage['compulsory_memory_owners'],self.coverage['required_target_owners']),
            (contract['compulsory_memory_owners'],contract['required_target_owners']))

    def test_actual_json_roundtrip_and_lossless_delivery(self):
        spec=json.loads(json.dumps(self.spec));self.assertEqual(spec,self.spec)
        self.assertEqual(c.Strict(spec).spec,self.spec)
        self.assertEqual(self.observer.count['rows'],self.observer.count['unmodified_delivered_rows'])
        self.assertEqual(self.observer.before.digest(),self.observer.after.digest())

    def test_host_clone_isolated_mutable_state(self):
        state=deepcopy(self.state);self.assertIs(state.gold,self.state.gold)
        state.calls[-1]['reads'].remove(8);self.assertIn(8,self.state.calls[-1]['reads'])
        state.regs[8]=999;self.assertNotEqual(self.state.regs.get(8),999)
        state.counts[0]+=9;state.console.append(255)
        self.assertNotEqual(state.counts,self.state.counts);self.assertNotEqual(state.console,self.state.console)
        state.active['reads'].discard(0);self.assertIn(0,self.state.active['reads'])
        observer=deepcopy(self.observer);observer.before.update(b'negative')
        self.assertNotEqual(observer.before.digest(),self.observer.before.digest())

    def test_observe_without_runtime_delivery_rejected(self):
        observer=c.OwnerObserver(self.protocol);observer.observe(self.abi[0])
        self.assertEqual(observer.count['rows'],1)
        self.assertEqual(observer.count['unmodified_delivered_rows'],0)
        with self.assertRaises(AssertionError):observer.finish()

    def test_actual_elf_abi(self):
        state=deepcopy(self.reset)
        for row in self.abi:state.consume(row)
        self.assertEqual(state.value(0x800fffe8,8),0x80000052)
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
        state,row=self.snapshots['entry'];state=deepcopy(state);state.fresh['out']-=set(range(24,32))
        with self.assertRaisesRegex(ValueError,'Deleted fresh'):state.consume(row)

    def test_seed_and_mask_complete_original_inputs(self):
        for name in ('a','b','mask'):
            state,row=self.snapshots['entry'];state=deepcopy(state);state.memory[state.s[name]+1]^=1
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'initialized values'):state.consume(row)

    def test_word_every_byte_and_guards(self):
        for key in ('word0','word64','active_word'):
            state,row=self.snapshots[key];size=c.memory_op(int(row['insn'],16))['size']
            for byte in range(size):
                with self.subTest(key=key,byte=byte),self.assertRaisesRegex(ValueError,'expected='):
                    deepcopy(state).consume(dict(row,rd_wdata=f'{int(row["rd_wdata"],16)^(1<<(8*byte)):016x}'))

    def test_tail_four_bytes_and_missing_read(self):
        state,row=self.snapshots['word64']
        with self.assertRaises(ValueError):deepcopy(state).consume(dict(row,mem_rmask='ff'))
        with self.assertRaises(ValueError):deepcopy(state).finish_call()
        state=deepcopy(self.state);state.calls[-1]['reads'].remove(8)
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
        self.assertEqual(sum(g['op']==24 and g['vstart']<g['vl'] for g in self.gold),c.owner_contract()['required_op24_memory_targets'])

    def test_generic_drop_arch_or_uop(self):
        observer=deepcopy(self.observer);observer.arch.pop()
        with self.assertRaises((ValueError,AssertionError)):observer.finish()
        observer=deepcopy(self.observer);observer.uops[0]=(0,0)
        with self.assertRaises((ValueError,AssertionError)):observer.finish()

    def test_empty_target_qualification(self):
        self.assertEqual(sum(not x['required'] for x in self.state.offloads if x['kind']=='target'),c.owner_contract()['elidable_target_owners'])
        self.assertEqual(sum(x['required'] for x in self.state.offloads if x['kind']=='memory'),c.owner_contract()['compulsory_memory_owners'])

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

    def test_typed16_physical_upper_and_high_byte(self):
        for name,offset in (('a',64),('b',2047),('mask',4),('out',68)):
            state,row=self.snapshots['entry'];state=deepcopy(state);state.memory[state.s[name]+offset]^=1
            with self.subTest(name=name),self.assertRaises(ValueError):state.consume(row)
        state,row=self.snapshots['word0']
        with self.assertRaises(ValueError):deepcopy(state).consume(dict(row,rd_wdata=f'{int(row["rd_wdata"],16)^0x100:016x}'))

    def test_initializer_schedule_typed_not_bytefill(self):
        state,row=self.snapshots['entry']
        self.assertEqual(len(state.spec['init_stores']),9)
        self.assertEqual([(x[2],x[3]) for x in state.spec['init_stores'] if x[2]==4],[(4,64)])
        state=deepcopy(state);state.memory[state.s['out']+1]=91
        with self.assertRaises(ValueError):state.consume(row)

    def test_retire_duplicate_reorder_and_instruction_drop(self):
        state,row=self.snapshots['entry']
        for field,value in (('order',str(int(row['order'])+1)),('pc',f'{int(row["pc"],16)+4:016x}'),
            ('insn',f'{int(row["insn"],16)^0x1000:08x}')):
            with self.subTest(field=field),self.assertRaises(ValueError):
                deepcopy(state).consume(dict(row,**{field:value}))

    def test_vi1_vi2_optional_and_vi3_deleted_owner_reject(self):
        for vl in (1,2,3):
            index=next(i for i,x in enumerate(self.state.offloads) if x['kind']=='target' and
                self.gold[x['call']]['op']==19 and self.gold[x['call']]['vl']==vl)
            item=self.coverage['owner_ledger'][index];seq=item['arch_order']
            self.assertEqual(item['insn'],0x38813c57)
            self.assertEqual(item['required'],vl==3)
            if vl==3:
                observer=deepcopy(self.observer);observer.owner_alloc[seq]=observer.owner_done[seq]=0
                with self.assertRaisesRegex(ValueError,'necessary architectural owner'):
                    observer.owner_coverage(self.state.offloads,dict(rows=self.gold,masks=[self.gold[i]['mask'] for i in (0,3,6)]))
            else:self.assertEqual((item['alloc'],item['done']),(0,0))

    def test_optional_target_existing_token_protocol_still_paired(self):
        c.common.image_context(r.IMAGE);observer=c.OwnerObserver(self.protocol)
        builder=Builder(self.spec)
        pc=self.spec['backend']['helpers']['op_19'][8]['pc'];row=builder.row(pc)
        row['insn']='38813c57';event=dict(row,event='cvx_req',order='0',trans_id='0',port='-1')
        for paired in (True,False):
            observer=c.OwnerObserver(self.protocol)
            class Rows:
                fieldnames=c.mature.transport.transport.FIELDS
                def __iter__(self):
                    yield event;yield dict(event,event='arch_start');yield dict(event,event='uop_alloc',port='0')
                    if paired:yield dict(event,event='uop_done',port='0')
                    yield dict(event,event='cvx_resp');yield row
            for item in observer.rows(Rows()):pass
            if paired:self.assertEqual(observer.finish()['backend_uop_done_count'],1)
            else:
                with self.assertRaises(AssertionError):observer.finish()

if __name__=='__main__':
    START_PINS={str(c.HERE/name):c.sha(c.HERE/name) for name in ('checker.py','replay.py','test_host.py','host_records.py','reset_profile.json')}
    r.durable(c.HERE/'host01_loaded_code_preflight.json',dict(pins=START_PINS,captured_before_tests=True,
        note='Imports occurred before this hash capture; no loaded-code byte attestation. Same disk files frozen throughout tests.'))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    pins=START_PINS
    c.common.base.verify_pins(pins)
    r.durable(c.HERE/'host01.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',tests=result.testsRun,
        failures=len(result.errors)+len(result.failures),pins=pins,input_pins_pre_post_unchanged=True,actual_abi_entry_checked=result.wasSuccessful(),full4095_streams=1,
        full_positive_shapes=[c.SHAPE] if result.wasSuccessful() else [],CSV_reads=0,DUT_reference_build_runs=0,
        fixture='Constructed source/actual-machine-site rows, not captured DUT or a scalar ISA emulator'))
    raise SystemExit(not result.wasSuccessful())
