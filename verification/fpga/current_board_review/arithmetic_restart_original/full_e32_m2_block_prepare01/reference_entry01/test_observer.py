"""Focused constructed lifecycle/EOF checks; no ISA, compiler or DUT execution."""
import unittest
from pathlib import Path
import tempfile
from context import artifacts
from lifecycle import *
from reference_check import audit
from raw_boundary import BOOT

class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s,cls.code,cls.helpers,cls.rows=artifacts()
        cls.entries=[cls.helpers[f'op_{i}'][0]['pc'] for i in range(35)]
    def state(self,call=0):
        state=Lifecycle(self.s,self.code,self.entries,self.rows)
        for address in range(self.s['__bss_start'],self.s['__bss_end'],8):state.store(BSS_PC,self.code[BSS_PC],address,8,0)
        state.enter(self.s['main']);state.enter(self.s['arithmetic_main'])
        if call:
            # Isolated negative-test snapshots, not accepted full-history proof.
            state.calls=call;state.seed_cursor=184*(self.rows[call]['seed']+1)
            state.cache_reads=state.cache_stores=8*(self.rows[call]['seed']+1);state.read_cursor=33
        return state
    def seed(self,state):
        while state.seed_cursor<184*(self.rows[state.calls]['seed']+1):
            _,pc,key,off,value=state.seed[state.seed_cursor]
            state.store(pc,self.code[pc],self.s[key]+off,4,value)
        while state.cache_stores<8*(self.rows[state.calls]['seed']+1):
            seed,k=divmod(state.cache_stores,8);value=FP_INPUTS[(seed+k)%8]
            state.read(CACHE_LOAD_PC,self.s['fp_inputs']+4*((seed+k)%8),4,lw_value(value))
            state.store(CACHE_STORE_PC,self.code[CACHE_STORE_PC],state.cache_base+4*k,4,value)
    def mask(self,state,omit=None,omit_load=None):
        previous=[0]*128
        for n,(pc,off,w,value,load) in enumerate(state.mask_wants[self.rows[state.calls]['mode']]):
            if load is not None and n!=omit_load:state.read(load,self.s['mask']+off,1,previous[off])
            if n!=omit:state.store(pc,self.code[pc],self.s['mask']+off,w,value)
            if w==1:previous[off]=value
    def fp(self,state,omit=None,omit_load=None):
        row=self.rows[state.calls]
        for n in range(128):
            i,bank=divmod(n,2);slot=(3*i if bank else i)%8;key=('a','b')[bank];value=row[key][i]
            if n!=omit_load:state.read(FP_LOAD_PC[n],state.cache_base+4*slot,4,lw_value(value))
            if n!=omit:state.store(FP_PC[n],self.code[FP_PC[n]],self.s[key]+4*i,4,value)
    def output(self,state,omit=None):
        for i,pc in enumerate(INIT_PC):
            if i!=omit:state.store(pc,self.code[pc],self.s['out']+8*i,8,SENTINEL)
    def reads(self,state,omit=None):
        for i,pc in enumerate(READ_PC):
            if i!=omit:state.read(pc,self.s['out']+8*i,8,self.rows[state.calls-1]['words'][i])
    def test_full5985_constructed_lifecycle(self):
        state=self.state()
        for row in self.rows:
            if state.seed_cursor<184*(row['seed']+1):self.seed(state)
            if row['si']==0:self.mask(state)
            if row['op']>=25:self.fp(state)
            self.output(state);state.enter(self.entries[row['op']]);self.reads(state)
        state.finish()
        self.assertEqual((state.fp_stores,state.mask_bit_stores,state.output_reads),(241920,77175,197505))
    def test_missing_equal_fp_every_SW_and_LW(self):
        self.assertEqual(self.rows[1365]['a'],self.rows[1366]['a'])
        for n in range(128):
            for load in (False,True):
                state=self.state(1366)
                with self.subTest(index=n,load=load),self.assertRaises(ValueError):
                    self.fp(state,omit_load=n if load else None,omit=None if load else n)
                    self.output(state);state.enter(self.entries[25])
    def test_FP_wrong_bank_value_width_slot_order(self):
        state=self.state(1366);value=self.rows[1366]['a'][0]
        for pc,address,size,value2 in [(FP_LOAD_PC[0],state.cache_base+4,4,lw_value(value)),
            (FP_LOAD_PC[1],state.cache_base,4,lw_value(value)),(FP_LOAD_PC[0],state.cache_base,8,value),
            (FP_LOAD_PC[0],state.cache_base,4,lw_value(value)^1)]:
            with self.assertRaises(ValueError):self.state(1366).read(pc,address,size,value2)
        for address,size,value2 in [(self.s['b'],4,value),(self.s['a'],8,value),(self.s['a'],4,value^1)]:
            state=self.state(1366);state.read(FP_LOAD_PC[0],state.cache_base,4,lw_value(value))
            with self.assertRaises(ValueError):state.store(FP_PC[0],self.code[FP_PC[0]],address,size,value2)
    def test_seed_cache_old_seed_missing_read_and_reorder(self):
        state=self.state()
        while state.seed_cursor<184:
            _,pc,key,off,v=state.seed[state.seed_cursor];state.store(pc,self.code[pc],self.s[key]+off,4,v)
        with self.assertRaises(ValueError):state.store(CACHE_STORE_PC,self.code[CACHE_STORE_PC],state.cache_base,4,FP_INPUTS[0])
        with self.assertRaises(ValueError):state.read(CACHE_LOAD_PC,self.s['fp_inputs']+4,4,lw_value(FP_INPUTS[1]))
        state.read(CACHE_LOAD_PC,self.s['fp_inputs'],4,lw_value(FP_INPUTS[0]))
        with self.assertRaises(ValueError):state.store(CACHE_STORE_PC,self.code[CACHE_STORE_PC],state.cache_base+4,4,FP_INPUTS[0])
        with self.assertRaises(ValueError):self.mask(state)
    def test_each_mask_clear_bit_load_missing(self):
        for n in range(80):
            state=self.state();self.seed(state)
            with self.subTest(n=n),self.assertRaises(ValueError):
                self.mask(state,omit=n);self.output(state);state.enter(self.entries[0])
        for n in (16,47,79):
            state=self.state();self.seed(state)
            with self.assertRaises(ValueError):self.mask(state,omit_load=n)
    def test_mask_wrong_owner_previous_value_and_early_load(self):
        with self.assertRaises(ValueError):self.mask(self.state(1))
        state=self.state();self.seed(state);first=state.mask_wants[0][16]
        with self.assertRaises(ValueError):state.read(first[4],self.s['mask'],1,0)
        for n,pc in enumerate(CLEAR_PC):state.store(pc,self.code[pc],self.s['mask']+8*n,8,0)
        with self.assertRaises(ValueError):state.read(first[4],self.s['mask'],1,1)
    def test_output_each_missing_and_last_width(self):
        for n in range(33):
            state=self.state();self.seed(state);self.mask(state)
            with self.assertRaises(ValueError):self.output(state,n);state.enter(self.entries[0])
            state=self.state();self.seed(state);self.mask(state);self.output(state);state.enter(self.entries[0])
            with self.assertRaises(ValueError):self.reads(state,n);self.output(state)
        for size in (2,4):
            state=self.state();self.seed(state);self.mask(state);self.output(state);state.enter(self.entries[0])
            for n,pc in enumerate(READ_PC[:-1]):state.read(pc,self.s['out']+8*n,8,0)
            with self.assertRaises(ValueError):state.read(READ_PC[-1],self.s['out']+256,size,0)
    def test_last_word_element63_and_guard(self):
        from reference_check import exact_word
        row=next(r for r in self.rows if r['expected'][63]!=91);expected=b''.join(v.to_bytes(8,'little') for v in row['words'])
        value=row['words'][-1];exact_word(expected,256,8,value)
        for value2 in (value^1,value^(1<<32)):
            with self.assertRaises(ValueError):exact_word(expected,256,8,value2)
        with self.assertRaises(ValueError):exact_word(expected,256,4,value&0xffffffff)
    def test_missing_complete_helper_owner_and_noop_not_waived(self):
        state=self.state();self.seed(state);self.mask(state);self.output(state)
        with self.assertRaises(ValueError):self.output(state)
        with self.assertRaises(ValueError):state.enter(self.entries[1])
        for call,row in enumerate(self.rows):
            if row['op']==19 and row['vl']<=2:
                state=self.state(call)
                with self.assertRaises(ValueError):state.enter(self.entries[19])
        state=self.state();state.calls=5985
        with self.assertRaises(ValueError):state.enter(self.entries[0])
    def test_partial_finish_fullphysical_code_drift(self):
        with self.assertRaises(ValueError):self.state().finish()
        for base in (8,16,24):
            self.assertEqual(full_group({base:0,base+1:0},base),bytes(256))
            with self.assertRaises(ValueError):full_group({base:0},base)
            with self.assertRaises(ValueError):full_group({base:0,base+1:1<<1024},base)
        code=dict(self.code);code[INIT_PC[-1]]=0x13
        with self.assertRaises(ValueError):Lifecycle(self.s,code,self.entries,self.rows)
    def test_parser_unknown_code_trap_and_partial(self):
        prefix=''.join(f'core 0: 3 0x{pc:016x} (0x{insn:08x}) {rest}\n' for pc,insn,rest in BOOT)
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'trace.log'
            for suffix in ('core 0: 3 0x0000000080000000 (0x00000013)\n','trap_illegal_instruction\n',''):
                raw.write_text(prefix+suffix)
                with self.assertRaises(ValueError):audit(raw)

if __name__=='__main__':unittest.main(verbosity=2)
