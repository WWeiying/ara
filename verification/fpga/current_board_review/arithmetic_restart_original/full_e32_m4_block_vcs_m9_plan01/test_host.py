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
START=time.monotonic()
def progress(stage,**values):print('HOST_STAGE',stage,'elapsed_s',round(time.monotonic()-START,3),values,flush=True)
progress('imports_begin')
import checker as c
import replay as r
from host_records import Builder
progress('imports_complete')

def deepcopy(value):
    if isinstance(value,c.Strict):
        result=copy(value)
        result.life=copy(value.life)
        result.counts=list(value.counts);result.console=bytearray(value.console)
        result.regs=value.regs.copy();result.memory=value.memory.copy()
        result.calls=[dict(call,reads=set(call['reads'])) for call in value.calls]
        result.active=result.calls[value.active['ordinal']] if value.active is not None else None
        result.offloads=[dict(offload) for offload in value.offloads]
        result.fresh={name:set(bits) for name,bits in value.fresh.items()}
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
        progress('spec_model_begin')
        cls.spec=c.specification();cls.gold=c.model();cls.reset=c.Strict(cls.spec)
        c.common.image_context(r.IMAGE);cls.protocol=sys.modules['ara_verify.trace']
        builder=Builder(cls.spec);cls.abi=list(builder.abi());cls.before_abi_store=deepcopy(cls.reset)
        for row in cls.abi[:-2]:cls.before_abi_store.consume(row)
        progress('abi_complete')
        state=c.Strict(cls.spec);observer=c.OwnerObserver(cls.protocol);cls.snapshots={}
        builder=Builder(cls.spec)
        class HostRows:
            fieldnames=c.mature.transport.transport.FIELDS
            def __iter__(self):return iter(builder.protocol_rows(builder.records()))
        fp_first={int(state.life.fp[k][8]['pc'],16):k for k in range(3)}
        fp_load=int(state.life.fp[0][0]['pc'],16)
        mask_first=int(state.life.mask[0][0]['pc'],16)
        mask_middle=int(state.life.mask[0][75]['pc'],16)
        cache_plan=state.life.machine.walk(state.life.packed,state.s['e32m4_expected_ids'],cls.gold[0]['raw'])
        expected_pc=next(int(e['pc'],16) for e in cache_plan['events'] if e['kind']=='GOLD')
        tag_pc=next(int(e['pc'],16) for e in cache_plan['branches'] if e['taint']==['ID'])
        snapshot_sites={'first_mask_store':mask_first,'mask_middle':mask_middle,'expected':expected_pc,'tag':tag_pc}
        next_progress=256
        progress('full5985_stream_begin')
        for row in observer.rows(HostRows()):
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
                for key,address in snapshot_sites.items():
                    if pc==address and key not in cls.snapshots:cls.snapshots[key]=(deepcopy(state),dict(row))
                if pc in fp_first:
                    key='fp_store'+str(fp_first[pc])
                    if key not in cls.snapshots:cls.snapshots[key]=(deepcopy(state),dict(row))
                if pc==fp_load:
                    key='fp_load'+str(cls.gold[state.life.calls]['seed'])
                    if key not in cls.snapshots:cls.snapshots[key]=(deepcopy(state),dict(row))
            state.consume(row)
            if len(state.calls)>=next_progress:
                progress('stream',calls=len(state.calls),rows=state.rows,retired=state.retired);next_progress+=256
        cls.state=state;cls.observer=observer
        cls.strict=state.finish();progress('strict_finish')
        cls.generic=observer.finish();progress('generic_finish')
        cls.coverage=observer.owner_coverage(state.offloads,dict(rows=state.gold,masks=[state.gold[i]['mask'] for i in (0,3,6)]))
        progress('owner_finish')

    def setUp(self):progress('test',name=self._testMethodName)
    def test_full5985_complete_data(self):
        self.assertEqual([self.strict[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads')],
            [5985,766080,11970,5985,77805,389025])
        self.assertEqual(self.strict['routine_counts'],[5985]*13)
        self.assertEqual({x['op'] for x in self.strict['call_ledger']},set(range(35)))
        self.assertEqual((self.generic['rows'],self.generic['retire_count']), (self.strict['rows'],self.strict['retired']))
        self.assertEqual((self.coverage['compulsory_memory_owners'],self.coverage['required_target_owners']), (c.owner_counts()['compulsory_memory_owners'],c.owner_counts()['required_target_owners']))


    def test_actual_json_roundtrip_and_lossless_delivery(self):
        spec=json.loads(json.dumps(self.spec));self.assertEqual(spec,self.spec)
        self.assertEqual(c.Strict(spec).spec,self.spec)
        self.assertEqual(self.observer.count['rows'],self.observer.count['unmodified_delivered_rows'])
        self.assertEqual(self.observer.before.digest(),self.observer.after.digest())


    def test_host_clone_isolated_mutable_state(self):
        state=deepcopy(self.state);self.assertIs(state.gold,self.state.gold)
        state.calls[-1]['reads'].remove(64);self.assertIn(64,self.state.calls[-1]['reads'])
        state.regs[8]=999;self.assertNotEqual(self.state.regs.get(8),999)
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
        self.assertEqual(state.value(0x800ffff8,8),0x80000052)
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
        state,row=self.snapshots['entry'];state=deepcopy(state);state.fresh['out']-=set(range(8,16))
        with self.assertRaisesRegex(ValueError,'All65 fresh|Deleted fresh'):state.consume(row)


    def test_seed_and_mask_complete_original_inputs(self):
        for name,offset in (('a',1),('b',1),('mask',1),('a',127),('b',127),('mask',127)):
            state,row=self.snapshots['entry'];state=deepcopy(state);state.memory[state.s[name]+offset]^=1
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'initialized values'):state.consume(row)


    def test_word_every_byte_and_guards(self):
        for key in ('word0','word512','active_word'):
            state,row=self.snapshots[key];size=c.memory_op(int(row['insn'],16))['size']
            for byte in range(size):
                with self.subTest(key=key,byte=byte),self.assertRaisesRegex(ValueError,'Exact linked source memory|expected='):
                    deepcopy(state).consume(dict(row,rd_wdata=f'{int(row["rd_wdata"],16)^(1<<(8*byte)):016x}'))


    def test_last_whole_word_and_missing_read(self):
        state,row=self.snapshots['word512']
        with self.assertRaises(ValueError):deepcopy(state).consume(dict(row,mem_rmask='03'))
        with self.assertRaises(ValueError):deepcopy(state).finish_call()
        state=deepcopy(self.state);state.calls[-1]['reads'].remove(64)
        with self.assertRaises(ValueError):state.finish()


    def test_vstart_and_true_failure_pc(self):
        state,row=self.snapshots['vstart']
        with self.assertRaisesRegex(ValueError,'returned vstart'):deepcopy(state).consume(dict(row,rd_wdata='0000000000000001'))
        state,row=self.snapshots['entry'];pc=state.spec['failure_pcs'][0]
        with self.assertRaisesRegex(ValueError,'failure/trap'):deepcopy(state).consume(dict(row,pc=f'{pc:016x}',insn=f'{state.code[pc]:08x}'))


    def test_required_active_target_and_op24_pair_deleted(self):
        for op in range(35):
            index=next(i for i,r0 in enumerate(self.state.offloads) if r0['kind']=='target' and r0['required'] and self.gold[r0['call']]['op']==op)
            seq=self.coverage['owner_ledger'][index]['arch_order']
            observer=deepcopy(self.observer);self.assertGreater(observer.owner_alloc[seq],0)
            observer.owner_alloc[seq]=observer.owner_done[seq]=0
            with self.subTest(op=op),self.assertRaisesRegex(ValueError,'necessary architectural owner'):
                observer.owner_coverage(self.state.offloads,dict(rows=self.gold,masks=[self.gold[i]['mask'] for i in (0,3,6)]))
        self.assertEqual(sum(g['op']==24 and g['vstart']<g['vl'] for g in self.gold),c.owner_counts()['required_op24_memory_targets'])


    def test_each_helper_owner_pair_deleted(self):
        for helper_index in (1,2,3,4,11):
            item=next(x for x in self.coverage['owner_ledger'] if x['kind']=='memory' and x['helper_index']==helper_index)
            observer=deepcopy(self.observer);order=item['arch_order']
            observer.owner_alloc[order]=observer.owner_done[order]=0
            with self.subTest(helper_index=helper_index),self.assertRaisesRegex(ValueError,'necessary architectural owner'):
                observer.owner_coverage(self.state.offloads,dict(rows=self.gold,masks=[self.gold[i]['mask'] for i in (0,3,6)]))


    def test_whole_fresh_input_mask_writes_missing(self):
        for name in ('a','b','mask'):
            original,row=self.snapshots['entry'];state=deepcopy(original);state.fresh[name].clear()
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'All65 fresh|Deleted fresh'):state.consume(row)


    def test_owner_wrong_id_and_fake_nonempty(self):
        item=next(x for x in self.coverage['owner_ledger'] if x['required'])
        observer=deepcopy(self.observer);order=item['arch_order']
        observer.owner_done[order]-=1;observer.owner_done[order+1]+=1
        with self.assertRaisesRegex(ValueError,'alloc/done'):
            observer.owner_coverage(self.state.offloads,dict(rows=self.gold,masks=[self.gold[i]['mask'] for i in (0,3,6)]))
        ledger=[dict(x) for x in self.state.offloads]
        next(x for x in ledger if x['kind']=='target' and not x['required'])['required']=True
        with self.assertRaisesRegex(ValueError,'Target required|necessary architectural owner'):
            self.observer.owner_coverage(ledger,dict(rows=self.gold,masks=[self.gold[i]['mask'] for i in (0,3,6)]))


    def test_generic_drop_arch_or_uop(self):
        observer=deepcopy(self.observer);observer.arch.pop()
        with self.assertRaises((ValueError,AssertionError)):observer.finish()
        observer=deepcopy(self.observer);observer.uops[0]=(0,0)
        with self.assertRaises((ValueError,AssertionError)):observer.finish()


    def test_empty_target_qualification(self):
        self.assertEqual(sum(not x['required'] for x in self.state.offloads if x['kind']=='target'),2223)
        self.assertEqual(sum(x['required'] for x in self.state.offloads if x['kind']=='memory'),29925)


    def short_owners(self,op,vl,mode=0):
        g=next(g for g in self.gold if g['op']==op and g['vl']==vl and g['mode']==mode and g['vstart']==0)
        helper=self.spec['backend']['helpers'][f'op_{op}'];ledger=[]
        for j in (1,2,3,4,8,11):
            target=j==8;insn=helper[j]['insn']
            ledger.append(dict(insn=insn,pc=helper[j]['pc'],retire_order=len(ledger),call=0,
                helper_index=j,kind='target' if target else 'memory',
                required=c.target_required(insn,g,self.spec) if target else True))
        observer=c.OwnerObserver(self.protocol)
        observer.arch=[x['insn'] for x in ledger];observer.retvec=list(observer.arch)
        for i,item in enumerate(ledger):
            if item['required']:observer.owner_alloc[i]=observer.owner_done[i]=1
        gold=dict(rows=[g],masks=[self.gold[i]['mask'] for i in (0,3,6)])
        return observer,ledger,gold


    def test_exact_slideup_noop_all18_and_short_controls(self):
        noops=[g for g in self.gold if g['vstart']<g['vl'] and not c.target_required(
            self.spec['backend']['helpers'][f'op_{g["op"]}'][8]['insn'],g,self.spec)]
        self.assertEqual(len(noops),18)
        self.assertEqual(c.owner_counts()['baseline_vstart_noops'],2205)
        self.assertEqual(c.owner_counts()['additional_exact_VI2_noops'],18)
        self.assertEqual({(g['op'],g['vl']) for g in noops},{(19,1),(19,2)})
        self.assertEqual({g['seed'] for g in noops},{0,1,2})
        for vl in (1,2):
            for mode in (0,1,2):
                observer,ledger,gold=self.short_owners(19,vl,mode)
                coverage=observer.owner_coverage(ledger,gold)
                self.assertEqual(coverage['required_target_owners'],0)
                self.assertEqual(coverage['minimum_required_owners'],5)
                self.assertEqual(observer.owner_alloc[4],0)
        for op,vl in ((19,3),(20,1),(20,2),(24,1)):
            observer,ledger,gold=self.short_owners(op,vl)
            self.assertEqual(observer.owner_coverage(ledger,gold)['required_target_owners'],1)
            observer.owner_alloc[4]=observer.owner_done[4]=0
            with self.subTest(op=op,vl=vl),self.assertRaisesRegex(ValueError,'necessary architectural owner'):
                observer.owner_coverage(ledger,gold)


    def test_noop_does_not_waive_helpers_or_tokens(self):
        for index in (0,1,2,3,5):
            observer,ledger,gold=self.short_owners(19,1)
            observer.owner_alloc[index]=observer.owner_done[index]=0
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'necessary architectural owner'):
                observer.owner_coverage(ledger,gold)
        observer,ledger,gold=self.short_owners(19,2)
        observer.owner_done[4]=1
        with self.assertRaisesRegex(ValueError,'alloc/done'):observer.owner_coverage(ledger,gold)
        observer,ledger,gold=self.short_owners(19,1)
        ledger[4]['required']=True
        with self.assertRaisesRegex(ValueError,'Target required'):observer.owner_coverage(ledger,gold)


    def test_noop_wrong_encoding_and_unrelated_target_rejected(self):
        observer,ledger,gold=self.short_owners(19,1);g=gold['rows'][0]
        for insn in (0x38813c57^(1<<15),0x38813c57^(1<<26),0x38813c57^(1<<12)):
            with self.subTest(insn=insn),self.assertRaisesRegex(ValueError,'encoding'):
                c.target_required(insn,g,self.spec)
        for op in (0,20,21,24):
            observer,ledger,gold=self.short_owners(op,1)
            ledger[4]['required']=False
            observer.owner_alloc[4]=observer.owner_done[4]=0
            with self.subTest(op=op),self.assertRaisesRegex(ValueError,'Target required'):
                observer.owner_coverage(ledger,gold)


    def test_typed32guards_highbits_signedzero_NaN_bitwise(self):
        for key in ('word0','word512','active_word'):
            state,row=self.snapshots[key]
            for delta in (1<<31,1<<63,0x80000000,0x7fc00000):
                with self.subTest(key=key,delta=delta),self.assertRaises(ValueError):
                    deepcopy(state).consume(dict(row,rd_wdata=f'{int(row["rd_wdata"],16)^delta:016x}'))
        self.assertEqual(int.from_bytes(self.gold[0]['raw'][:4],'little'),91)
        self.assertEqual(int.from_bytes(self.gold[0]['raw'][-4:],'little'),91)


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


    def test_three_actual_FP_paths_strict_site_bank_and_freshness(self):
        for seed in range(3):
            state,row=self.snapshots['fp_store'+str(seed)]
            self.assertEqual(state.gold[state.life.calls]['ordinal']+1,(1366,3361,5356)[seed])
            for key,value in (('mem_addr',f'{state.s["b"]:016x}'),('mem_wmask','ff'),
                ('mem_wdata',f'{int(row["mem_wdata"],16)^1:016x}')):
                with self.subTest(seed=seed,key=key),self.assertRaises(ValueError):deepcopy(state).consume(dict(row,**{key:value}))
            life=copy(state.life);events=life.fp[seed]
            for event_index in (8,9,263):
                bad=copy(life)
                with self.subTest(seed=seed,skip=event_index),self.assertRaises(ValueError):
                    for i,e in enumerate(events[8:],8):
                        if i!=event_index:bad.store(int(e['pc'],16),state.code[int(e['pc'],16)],e['address'],e['size'],e['value'])
                    e=bad.init[0];bad.store(int(e['pc'],16),state.code[int(e['pc'],16)],e['address'],e['size'],e['value'])
            wrong=events[8].copy();wrong['pc']=life.fp[(seed+1)%3][8]['pc']
            with self.assertRaises(ValueError):
                copy(life).store(int(wrong['pc'],16),state.code[int(wrong['pc'],16)],wrong['address'],4,wrong['value'])

    def test_three_FP_loads_no_seed0_classifier(self):
        for seed in range(3):
            state,row=self.snapshots['fp_load'+str(seed)]
            self.assertEqual(state.life.fp_cursor,0)
            for key,value in (('mem_addr',f'{state.s["a"]:016x}'),('mem_rmask','ff'),('rd_wdata',f'{int(row["rd_wdata"],16)^1:016x}')):
                with self.subTest(seed=seed,key=key),self.assertRaises(ValueError):deepcopy(state).consume(dict(row,**{key:value}))

    def test_cache_firstfill_tag_and_all_actual_reads(self):
        for key in ('expected','word0','word512'):
            original,row=self.snapshots[key]
            state=deepcopy(original);state.life.cache_mem_cursor+=1
            with self.subTest(key=key),self.assertRaises(ValueError):state.consume(row)
        state,row=self.snapshots['tag'];state=deepcopy(state)
        insn=int(row['insn'],16);state.regs[(insn>>15)&31]^=1
        with self.assertRaises(ValueError):state.consume(row)
        state,row=self.snapshots['expected'];state=deepcopy(state);state.life.cache_pc_cursor+=1
        with self.assertRaises(ValueError):state.consume(row)

    def test_constant_mask_cumulative_value_and_missing_clear(self):
        state,row=self.snapshots['mask_middle']
        with self.assertRaises(ValueError):deepcopy(state).consume(dict(row,mem_wdata=f'{int(row["mem_wdata"],16)^1:016x}'))
        state,row=self.snapshots['first_mask_store'];life=state.life;events=life.mask[0]
        self.assertEqual(len(events),144)
        for skip in (0,15,16,75,143):
            q=copy(life)
            with self.subTest(skip=skip),self.assertRaises(ValueError):
                for i,e in enumerate(events):
                    if i!=skip:q.store(int(e['pc'],16),state.code[int(e['pc'],16)],e['address'],e['size'],e['value'])
                e=q.init[0];q.store(int(e['pc'],16),state.code[int(e['pc'],16)],e['address'],e['size'],e['value'])

    def test_exact_full_m4_lifecycle_counts(self):
        self.assertEqual([self.strict[k] for k in ('FP_calls','FP_input_scalar_writes','FP_source_reads','expected_reads','ID_reads','cache_hits','cache_misses','mask_clear_stores','mask_bit_stores','original_seed_scalar_writes')],
            [1890,483840,15120,124041,53865,33123,14757,35280,154350,1104])
        self.assertEqual(self.spec['config']['physical_group_registers'],4)
        self.assertEqual(self.spec['main_frame'],272)
        self.assertEqual(len(self.spec['FP_store_union']),768)
        for g in self.gold:self.assertEqual((len(g['raw']),len(g['a']),len(g['b']),len(g['mask'])),(520,128,128,128))

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    pins={str(c.HERE/name):c.sha(c.HERE/name) for name in ('checker.py','replay.py','test_host.py','host_records.py','reset_profile.json','lifecycle.py')}
    r.durable(c.HERE/'host01.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',tests=result.testsRun,
        failures=len(result.errors)+len(result.failures),pins=pins,actual_abi_entry_checked=result.wasSuccessful(),full5985_streams=1,
        full_positive_shapes=[c.SHAPE] if result.wasSuccessful() else [],CSV_reads=0,DUT_reference_build_runs=0,
        fixture='Constructed source/actual-machine-site rows, not captured DUT or a scalar ISA emulator'))
    raise SystemExit(not result.wasSuccessful())
