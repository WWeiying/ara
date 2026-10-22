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
        progress('spec_model_reset_complete',owners=c.owner_counts())
        c.common.image_context(r.IMAGE);cls.protocol=sys.modules['ara_verify.trace']
        progress('image_complete')
        builder=Builder(cls.spec);cls.abi=list(builder.abi())
        cls.before_abi_store=deepcopy(cls.reset)
        for row in cls.abi[:-2]:cls.before_abi_store.consume(row)
        progress('abi_complete')
        state=c.Strict(cls.spec);observer=c.OwnerObserver(cls.protocol)
        cls.snapshots={};builder=Builder(cls.spec)
        class HostRows:
            fieldnames=c.mature.transport.transport.FIELDS
            def __iter__(self):return iter(builder.protocol_rows(builder.records()))
        progress('full5985_stream_begin');next_progress=256
        for row in observer.rows(HostRows()):
            pc=int(row['pc'],16)
            if row['event']=='retire':
                site=state.lookup.get(pc)
                if site and site[0]=='op_0' and site[1]==0 and not state.calls:cls.snapshots['entry']=(deepcopy(state),dict(row))
                if site and site[0]=='op_0' and site[1]==9 and len(state.calls)==1:cls.snapshots['vstart']=(deepcopy(state),dict(row))
                if int(row['mem_rmask'],16) and state.active:
                    offset=int(row['mem_addr'],16)-state.s['out']
                    if offset in (0,256) and state.active['ordinal']==0:cls.snapshots['word'+str(offset)]=(deepcopy(state),dict(row))
                    if state.active['vl'] and state.active['vstart']<state.active['vl'] and offset==0 and 'active_word' not in cls.snapshots:
                        cls.snapshots['active_word']=(deepcopy(state),dict(row))
                if pc==state.spec['exit_store']:cls.snapshots['exit']=(deepcopy(state),dict(row))
            if row['event']=='retire' and state.init_index==1 and not state.calls and 'after_first_sd' not in cls.snapshots:
                cls.snapshots['after_first_sd']=(deepcopy(state),dict(row))
            if row['event']=='retire':
                for key,address in (('cache_read',c.lifecycle.CACHE_LOAD_PC),('cache_store',c.lifecycle.CACHE_STORE_PC),
                    ('fp_read',c.lifecycle.FP_LOAD_PC[0]),('mask_read',c.lifecycle.mask_schedule(0)[16][4])):
                    if pc==address and key not in cls.snapshots:cls.snapshots[key]=(deepcopy(state),dict(row))
                if pc==c.lifecycle.FP_PC[0] and 'first_fp_store' not in cls.snapshots:
                    cls.snapshots['first_fp_store']=(deepcopy(state),dict(row))
                if site and site[0]!='capacity' and site[1]==0 and state.gold[len(state.calls)]['op']>=25 and state.gold[len(state.calls)]['si']==1 and 'second_fp_entry' not in cls.snapshots:
                    cls.snapshots['second_fp_entry']=(deepcopy(state),dict(row))
                if pc==c.lifecycle.CLEAR_PC[0] and 'first_mask_store' not in cls.snapshots:
                    cls.snapshots['first_mask_store']=(deepcopy(state),dict(row))
            state.consume(row)
            if len(state.calls)>=next_progress:
                progress('stream',calls=len(state.calls),rows=state.rows,retired=state.retired)
                next_progress+=256
        progress('full_stream_complete',rows=state.rows,calls=len(state.calls))
        cls.state=state;cls.observer=observer
        cls.strict=state.finish();progress('strict_finish')
        cls.generic=observer.finish();progress('generic_finish')
        cls.coverage=observer.owner_coverage(state.offloads,dict(rows=state.gold,masks=[state.gold[i]['mask'] for i in (0,3,6)]))
        progress('owner_finish')

    def setUp(self):progress('negative_or_assert_start',name=self._testMethodName)
    def tearDown(self):progress('negative_or_assert_end',name=self._testMethodName)

    def test_full5985_complete_data(self):
        self.assertEqual([self.strict[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads')],
            [5985,383040,11970,5985,77805,197505])
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
        state.calls[-1]['reads'].remove(32);self.assertIn(32,self.state.calls[-1]['reads'])
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
        state,row=self.snapshots['entry'];state=deepcopy(state);state.fresh['out']-=set(range(8,16))
        with self.assertRaisesRegex(ValueError,'All33 output|Deleted fresh'):state.consume(row)

    def test_seed_and_mask_complete_original_inputs(self):
        for name,offset in (('a',1),('b',1),('mask',1),('a',127),('b',127),('mask',127)):
            state,row=self.snapshots['entry'];state=deepcopy(state);state.memory[state.s[name]+offset]^=1
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'initialized values'):state.consume(row)

    def test_actual_e32_group_gather_and_FP_bits(self):
        self.assertEqual((self.spec['config']['cap'],self.spec['config']['vtype'],
            self.spec['config']['physical_group_registers'],self.spec['config']['observed_group_bytes'],
            self.spec['config']['mask_bytes'],self.spec['config']['vlm_bytes']),(64,17,2,256,128,8))
        for g in self.gold:
            self.assertEqual((len(g['a']),len(g['b']),len(g['raw']),len(g['mask'])),(64,64,264,128))
            self.assertEqual(g['mask'][8:],[0]*120)
            if g['op']==21 and g['vl']>=3 and g['mode']==0:
                self.assertEqual(g['b'][2],0xffffffff);self.assertEqual(g['expected'][2],0)
        self.assertEqual((self.strict['FP_calls'],self.strict['FP_input_scalar_writes'],
            self.strict['mask_clear_stores'],self.strict['mask_bit_stores']),(1890,241920,35280,77175))
        self.assertEqual((self.strict['seed_cache_reads'],self.strict['seed_cache_stores'],self.strict['FP_cache_reads']),(24,24,241920))

    def test_word_every_byte_and_guards(self):
        for key in ('word0','word256','active_word'):
            state,row=self.snapshots[key];size=c.memory_op(int(row['insn'],16))['size']
            for byte in range(size):
                with self.subTest(key=key,byte=byte),self.assertRaisesRegex(ValueError,'expected='):
                    deepcopy(state).consume(dict(row,rd_wdata=f'{int(row["rd_wdata"],16)^(1<<(8*byte)):016x}'))

    def test_last_whole_word_and_missing_read(self):
        state,row=self.snapshots['word256']
        with self.assertRaises(ValueError):deepcopy(state).consume(dict(row,mem_rmask='03'))
        with self.assertRaises(ValueError):deepcopy(state).finish_call()
        state=deepcopy(self.state);state.calls[-1]['reads'].remove(32)
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

    def test_first_sd_not_completion(self):
        state,_=self.snapshots['after_first_sd'];self.assertEqual(state.init_index,1)
        self.assertEqual(len(state.fresh['out']),8)
        _,entry=self.snapshots['entry']
        builder=Builder(self.spec);builder.order=state.retired;builder.regs=state.regs.copy()
        for reg,value in enumerate([state.s['a'],state.s['b'],state.s['out']+4,0,64,state.s['mask'],0],10):
            state=deepcopy(state);state.consume(builder.setreg(reg,value))
        entry=dict(entry,order=str(state.retired),cycle=str(state.retired+1))
        with self.assertRaisesRegex(ValueError,'All33 output|initialized values out|Deleted fresh|initializer'):state.consume(entry)

    def test_each_helper_owner_pair_deleted(self):
        for helper_index in (1,2,3,4,11):
            item=next(x for x in self.coverage['owner_ledger'] if x['kind']=='memory' and x['helper_index']==helper_index)
            observer=deepcopy(self.observer);order=item['arch_order']
            observer.owner_alloc[order]=observer.owner_done[order]=0
            with self.subTest(helper_index=helper_index),self.assertRaisesRegex(ValueError,'necessary architectural owner'):
                observer.owner_coverage(self.state.offloads,dict(rows=self.gold,masks=[self.gold[i]['mask'] for i in (0,3,6)]))

    def test_first_sd_stale_matching_shadow_still_rejected(self):
        original,_=self.snapshots['after_first_sd'];state=deepcopy(original)
        self.assertEqual(state.init_index,1)
        for i,value in enumerate(c.lifecycle.words([91]*66)):state.memory[state.s['out']+i]=value
        builder=Builder(self.spec);builder.order=state.retired;builder.regs=state.regs.copy()
        for reg,value in enumerate([state.s['a'],state.s['b'],state.s['out']+4,0,64,state.s['mask'],0],10):
            state.consume(builder.setreg(reg,value))
        _,row=self.snapshots['entry'];row=dict(row,order=str(state.retired),cycle=str(state.retired+1))
        with self.assertRaisesRegex(ValueError,'All33 output|Deleted fresh'):state.consume(row)

    def test_whole_fresh_input_mask_writes_missing(self):
        for name in ('a','b','mask'):
            original,row=self.snapshots['entry'];state=deepcopy(original);state.fresh[name].clear()
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'All33 output|Deleted fresh'):state.consume(row)

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

    def test_FP_every_call_even_when_previous_values_equal(self):
        original,row=self.snapshots['second_fp_entry']
        for missing in range(128):
            state=deepcopy(original);state.life.fp_cursor=missing
            with self.subTest(missing=missing),self.assertRaisesRegex(ValueError,'128 paired cache LW/SW'):
                state.consume(row)
        state=deepcopy(original);state.memory[state.s['a']+3]^=0x80
        with self.assertRaisesRegex(ValueError,'initialized values a'):state.consume(row)

    def test_cache_and_FP_load_real_address_value_width_and_missing(self):
        for key in ('cache_read','fp_read','mask_read'):
            original,row=self.snapshots[key]
            for field,value in (('mem_addr',f'{int(row["mem_addr"],16)+4:016x}'),
                ('rd_wdata',f'{int(row["rd_wdata"],16)^1:016x}'),('mem_rmask','ff')):
                with self.subTest(key=key,field=field),self.assertRaises(ValueError):
                    deepcopy(original).consume(dict(row,**{field:value}))
        for key,attr in (('cache_store','cache_pending'),('first_fp_store','fp_pending')):
            original,row=self.snapshots[key];state=deepcopy(original);setattr(state.life,attr,None)
            with self.subTest(key=key),self.assertRaises(ValueError):state.consume(row)

    def test_cache_seed_identity_cannot_be_reused(self):
        original,row=self.snapshots['cache_store']
        state=deepcopy(original);state.life.cache_pending=(1,0)
        with self.assertRaisesRegex(ValueError,'Cache exact ordered'):state.consume(row)
        state=deepcopy(original);state.life.seed_cursor-=1
        with self.assertRaisesRegex(ValueError,'Cache source seed'):state.consume(row)

    def test_FP_wrong_site_bank_value_and_phase(self):
        state,row=self.snapshots['first_fp_store']
        for key,value in (('mem_addr',f'{state.s["b"]:016x}'),('mem_wmask','ff'),
                          ('mem_wdata',f'{int(row["mem_wdata"],16)^0x80000000:016x}')):
            with self.subTest(key=key),self.assertRaises(ValueError):
                deepcopy(state).consume(dict(row,**{key:value}))
        life=copy(state.life);g=state.gold[life.calls]
        # Starting immediately before first SW, retain its preceding LW.
        for skip in range(128):
            candidate=copy(life)
            with self.subTest(skip=skip),self.assertRaises(ValueError):
                for j,pc in enumerate(c.lifecycle.FP_PC):
                    i,bank=divmod(j,2);key=('a','b')[bank];slot=(3*i if bank else i)%8
                    if j:
                        candidate.read(c.lifecycle.FP_LOAD_PC[j],candidate.cache_base+4*slot,4,c.lifecycle.lw_value(g[key][i]))
                    if j!=skip:candidate.store(pc,state.code[pc],state.s[key]+i*4,4,g[key][i])
                candidate.store(c.lifecycle.INIT_PC[0],state.code[c.lifecycle.INIT_PC[0]],state.s['out'],8,c.lifecycle.SENTINEL)

    def test_every_ordered_mask_clear_and_bitset_write_required(self):
        state,row=self.snapshots['first_mask_store'];life=state.life
        schedule=c.lifecycle.mask_schedule(0)
        self.assertEqual(len(schedule),80)
        for skip in range(len(schedule)):
            candidate=copy(life);previous={}
            with self.subTest(skip=skip),self.assertRaises(ValueError):
                for i,(pc,offset,width,value,load) in enumerate(schedule):
                    if load is not None:candidate.read(load,state.s['mask']+offset,1,previous.get(offset,0))
                    if i!=skip:candidate.store(pc,state.code[pc],state.s['mask']+offset,width,value)
                    if width==1:previous[offset]=value
                candidate.store(c.lifecycle.INIT_PC[0],state.code[c.lifecycle.INIT_PC[0]],state.s['out'],8,c.lifecycle.SENTINEL)
        pc,offset,size,value,load=schedule[16]
        with self.assertRaises(ValueError):copy(life).store(pc,state.code[pc],state.s['mask']+offset,size,value)

    def test_typed32guards_highbits_signedzero_NaN_bitwise(self):
        for key in ('word0','word256','active_word'):
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

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    pins={str(c.HERE/name):c.sha(c.HERE/name) for name in ('checker.py','replay.py','test_host.py','host_records.py','reset_profile.json','lifecycle.py')}
    r.durable(c.HERE/'host01.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',tests=result.testsRun,
        failures=len(result.errors)+len(result.failures),pins=pins,actual_abi_entry_checked=result.wasSuccessful(),full5985_streams=1,
        full_positive_shapes=[c.SHAPE] if result.wasSuccessful() else [],CSV_reads=0,DUT_reference_build_runs=0,
        fixture='Constructed source/actual-machine-site rows, not captured DUT or a scalar ISA emulator'))
    raise SystemExit(not result.wasSuccessful())
