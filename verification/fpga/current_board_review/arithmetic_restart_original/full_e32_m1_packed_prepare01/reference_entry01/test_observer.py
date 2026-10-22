"""Constructed Host events only; no ISA execution, no reference replacement."""
from context import artifacts
from lifecycle import *
from raw_boundary import BOOT
from reference_check import audit
from pathlib import Path
import tempfile
import unittest

class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s,cls.code,cls.h,cls.rows=artifacts()
        cls.entries=[cls.h[f'op_{i}'][0]['pc'] for i in range(35)]
    def state(self,call=0):
        s=Lifecycle(self.s,self.code,self.entries,self.rows)
        for a in range(self.s['__bss_start'],self.s['__bss_end'],8):s.store(BSS_PC,self.code[BSS_PC],a,8,0)
        s.enter(self.s['main']);s.enter(self.s['arithmetic_main'])
        # Focused unit snapshots; the full constructed-parser test below proves
        # the complete predecessor history instead of relying on these snapshots.
        if call:s.calls=call;s.seed_cursor=92;s.read_cursor=17
        return s
    def seed(self,s):
        while s.seed_cursor<92*(self.rows[s.calls]['seed']+1):
            _,pc,key,offset,val=s.seed[s.seed_cursor]
            s.store(pc,self.code[pc],self.s[key]+offset,4,val)
    def mask(self,s,omit=None):
        for n,(pc,off,w,val) in enumerate(mask_schedule(self.rows[s.calls]['mode'])):
            if n!=omit:s.store(pc,self.code[pc],self.s['mask']+off,w,val)
    def fp(self,s,omit=None):
        row=self.rows[s.calls]
        for i in range(32):
            for bank,key in enumerate(('a','b')):
                if 2*i+bank!=omit:s.store(FP_PC[bank],self.code[FP_PC[bank]],self.s[key]+4*i,4,row[key][i])
    def output(self,s,omit=None):
        for i,pc in enumerate(INIT_PC):
            if i!=omit:s.store(pc,self.code[pc],self.s['out']+8*i,8,SENTINEL)
    def test_all5985_constructed_parser(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'constructed.log'
            with p.open('w') as f:
                def emit(pc,rest=''):f.write(f'core 0: 3 0x{pc:016x} (0x{self.code[pc]:08x}){rest}\n')
                def rd(pc,n,v):emit(pc,f' x{n} 0x{v:016x}')
                def store(pc,addr,val):emit(pc,f' mem 0x{addr:016x} 0x{val:016x}')
                for pc,insn,rest in BOOT:f.write(f'core 0: 3 0x{pc:016x} (0x{insn:08x}) {rest}\n')
                emit(0x80000000);emit(0x8000002a);emit(0x8000002e)
                for addr in range(self.s['__bss_start'],self.s['__bss_end'],8):store(BSS_PC,addr,0)
                emit(self.s['main']);emit(self.s['arithmetic_main'])
                cap=self.h['capacity']
                rd(cap[0]['pc'],5,(1<<64)-1)
                emit(cap[1]['pc'],' x10 0x0000000000000020 c3104_vl 0x20 c3105_vtype 0x10')
                emit(cap[2]['pc'])
                seeds=seed_schedule();cursor=0
                for row in self.rows:
                    while cursor<92*(row['seed']+1):
                        _,pc,key,off,val=seeds[cursor];store(pc,self.s[key]+off,val);cursor+=1
                    if row['si']==0:
                        for pc,off,_,val in mask_schedule(row['mode']):store(pc,self.s['mask']+off,val)
                    if row['op']>=25:
                        for i in range(32):
                            for bank,key in enumerate(('a','b')):store(FP_PC[bank],self.s[key]+4*i,row[key][i])
                    for i,pc in enumerate(INIT_PC):store(pc,self.s['out']+i*8,SENTINEL)
                    for pc,n,val in ((0x800005d2,10,self.s['a']),(0x800005ca,11,self.s['b']),
                        (0x800005c2,12,self.s['out']+4),(0x8000056e,13,row['vl']),
                        (0x8000056c,14,32),(0x800005ba,15,self.s['mask']),(0x80000a5a,16,row['start'])):rd(pc,n,val)
                    result=words(row['expected']);expected=b''.join(w.to_bytes(8,'little') for w in row['words'])
                    for j,item in enumerate(self.h[f'op_{row["op"]}']):
                        rest=''
                        if j in (0,5,10):rest=f' x5 0x{row["vl"] if j==5 else 32:016x} c3104_vl 0x{row["vl"] if j==5 else 32:x} c3105_vtype 0x10'
                        if j in (1,2,3):
                            data=words(row['a'] if j==1 else row['b'] if j==2 else [91]*32)
                            rest=f' v{(8,16,24)[j-1]} 0x{int.from_bytes(data,"little"):0256x}'
                        if j==4:rest=f' v0 0x{int.from_bytes(bytes(row["mask"][:4]),"little"):0256x}'
                        if j==6:rest=' x28 0x0000000000000007'
                        if j==7:rest=f' c8_vstart 0x{row["start"]:x}'
                        if j==8:rest=f' v24 0x{int.from_bytes(result,"little"):0256x} c8_vstart 0x0'
                        if j==9:rest=' x10 0x0000000000000000'
                        emit(item['pc'],rest)
                    for i,pc in enumerate(READ_PC):
                        emit(pc,f' x{(self.code[pc]>>7)&31} 0x{int.from_bytes(expected[8*i:8*i+8],"little"):016x} mem 0x{self.s["out"]+8*i:016x}')
                    store(0x80000922,self.s['elements'],row['ordinal']*32)
                    store(0x8000092e,self.s['checks'],row['ordinal'])
                text='RVV_MATRIX_PASS sew=32 vlmax=32 cases=5985 elements=191520 errors=0 seeds=3 guard_tail_mask_vstart=checked\n'
                for i,b in enumerate(text.encode()):store(0x800014cc,self.s['replay_log']+i,b)
                rd(self.s['replay_exit'],10,0);rd(0x8000006a,10,1)
                store(0x8000007a,self.s['tohost'],1);emit(0x8000007e)
            result=audit(p)
            self.assertEqual((result['calls'],result['packed_output_reads'],result['FP_input_scalar_writes']),(5985,101745,120960))
            self.assertEqual((result['helper_instructions'],result['mask_clear_stores'],result['mask_bit_stores']),(77805,35280,38955))
            self.assertTrue(result['EOF_checked']);self.assertFalse(result['fflags_oracle'])
    def test_each_missing_output_store(self):
        for i in range(17):
            s=self.state();self.seed(s);self.mask(s)
            with self.subTest(i=i),self.assertRaises(ValueError):self.output(s,i);s.enter(self.entries[0])
    def test_each_missing_clear_or_bitset(self):
        for i in range(48):
            s=self.state();self.seed(s)
            with self.subTest(i=i),self.assertRaises(ValueError):self.mask(s,i);self.output(s);s.enter(self.entries[0])
    def test_missing_equal_FP_each_bank_index(self):
        self.assertEqual(self.rows[1365]['a'],self.rows[1366]['a'])
        for i in range(64):
            s=self.state(1366)
            with self.subTest(i=i),self.assertRaises(ValueError):self.fp(s,i);self.output(s);s.enter(self.entries[25])
    def test_mask_wrong_owner_upper_bytes_value(self):
        s=self.state(1)
        with self.assertRaises(ValueError):self.mask(s)
        for i in (0,15):
            s=self.state();self.seed(s)
            with self.assertRaises(ValueError):
                for n,pc in enumerate(CLEAR_PC):s.store(pc,self.code[pc],self.s['mask']+8*n,8,1 if n==i else 0)
    def test_FP_wrong_site_bank_value_width(self):
        for args in ((FP_PC[0]+4,self.s['a'],4,self.rows[1365]['a'][0]),
                     (FP_PC[0],self.s['b'],4,self.rows[1365]['a'][0]),
                     (FP_PC[0],self.s['a'],8,self.rows[1365]['a'][0]),
                     (FP_PC[0],self.s['a'],4,self.rows[1365]['a'][0]^1)):
            s=self.state(1366)
            with self.assertRaises(ValueError):s.store(args[0],self.code[args[0]],*args[1:])
    def test_FP_in_integer_or_nextseed_owner(self):
        with self.assertRaises(ValueError):self.fp(self.state())
        s=self.state(1995)
        with self.assertRaises(ValueError):self.output(s);s.enter(self.entries[0])
    def test_last_full_word_not_tail(self):
        for omitted in range(17):
            s=self.state();self.seed(s);self.mask(s);self.output(s);s.enter(self.entries[0])
            with self.assertRaises(ValueError):
                for i,pc in enumerate(READ_PC):
                    if i!=omitted:s.read(pc,self.s['out']+8*i,8)
                self.output(s);s.enter(self.entries[0])
        for size in (2,4):
            s=self.state();self.seed(s);self.mask(s);self.output(s);s.enter(self.entries[0])
            for i,pc in enumerate(READ_PC[:-1]):s.read(pc,self.s['out']+8*i,8)
            with self.assertRaises(ValueError):s.read(READ_PC[-1],self.s['out']+128,size)
    def test_output_wrong_address_width_value(self):
        pc=INIT_PC[0]
        for addr,size,val in ((self.s['out']+1,8,SENTINEL),(self.s['out'],4,SENTINEL),(self.s['out'],8,0)):
            with self.assertRaises(ValueError):self.state().store(pc,self.code[pc],addr,size,val)
    def test_missing_seed_even_equal_shadow(self):
        s=self.state()
        with self.assertRaises(ValueError):self.mask(s);self.output(s);s.enter(self.entries[0])
    def test_wrong_helper_or_extra(self):
        s=self.state();self.seed(s);self.mask(s);self.output(s)
        with self.assertRaises(ValueError):s.enter(self.entries[1])
        s.calls=5985
        with self.assertRaises(ValueError):s.enter(self.entries[34])
    def test_physical_full128(self):
        for r in (8,16,24):
            self.assertEqual(full_group({r:0},r),bytes(128))
            self.assertNotEqual(full_group({r:1<<1023},r),bytes(128))
            with self.assertRaises(ValueError):full_group({},r)
            with self.assertRaises(ValueError):full_group({r:1<<1024},r)
    def test_partial_startup_late_clear(self):
        s=Lifecycle(self.s,self.code,self.entries,self.rows)
        with self.assertRaises(ValueError):s.enter(self.s['main'])
        s=self.state()
        with self.assertRaises(ValueError):s.store(BSS_PC,self.code[BSS_PC],self.s['out'],8,0)
    def test_partial_finish_and_code_drift(self):
        with self.assertRaises(ValueError):self.state().finish()
        code=dict(self.code);code[INIT_PC[0]]=0x13
        with self.assertRaises(ValueError):Lifecycle(self.s,code,self.entries,self.rows)
if __name__=='__main__':unittest.main(verbosity=2)
