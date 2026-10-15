"""Small constructed lifecycle boundary tests, not a fulltrace/reference substitute."""
import unittest
from context import artifacts
from lifecycle import *
from raw_boundary import RawBoundary,BOOT
from owner_contract import target_required
class EntryHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.s,cls.code,cls.h,cls.rows=artifacts();cls.entries=[cls.h[f'op_{i}'][0]['pc'] for i in range(35)]
    def initial(self):
        s=Lifecycle(self.s,self.code,self.entries,self.rows)
        for address in range(self.s['__bss_start'],self.s['__bss_end'],8):s.store(BSS_PC,self.code[BSS_PC],address,8,0)
        s.enter(self.s['main']);s.enter(self.s['arithmetic_main']);return s
    def setup(self):
        s=self.initial()
        for _,pc,key,off,val in s.seed[:92]:s.store(pc,self.code[pc],self.s[key]+off,8,val)
        for pc,off,w,val in mask_schedule(0):s.store(pc,self.code[pc],self.s['mask']+off,w,val)
        return s
    def output(self,s,omit=None):
        for i,pc in enumerate(INIT_PC):
            if i!=omit:s.store(pc,self.code[pc],self.s['out']+8*i,8,91)
    def fp_snapshot(self,call):
        # Explicit unit snapshot; no claim that omitted predecessor calls executed.
        s=self.initial();s.calls=call;s.seed_cursor=92*(self.rows[call]['seed']+1);s.read_cursor=34
        if self.rows[call]['si']==0:
            for pc,off,w,val in mask_schedule(self.rows[call]['mode']):s.store(pc,self.code[pc],self.s['mask']+off,w,val)
        return s
    def feed_clone(self,s,omit=None,swap=False,duplicate=False):
        row=self.rows[s.calls];path=FP_PATHS[row['seed']];stores={int(e['pc'],16):e for e in path['stores']};loads={int(e['pc'],16):e for e in path['loads']}
        for rawpc in path['pcs']:
            pc=int(rawpc,16);s.enter(pc)
            if pc in loads:s.read(pc,self.s['fp_inputs']+8*loads[pc]['table_index'],8)
            if pc in stores:
                event=stores[pc];bank,i=event['bank'],event['index'];n=2*i+(bank=='b')
                if n==omit:continue
                if swap and i==31:bank='b' if bank=='a' else 'a'
                s.store(pc,self.code[pc],self.s[bank]+8*i,8,row[bank][i])
                if duplicate and n==62:s.store(pc,self.code[pc],self.s[bank]+8*i,8,row[bank][i])
    def test_full_fresh_and_last_guard(self):
        s=self.setup();self.output(s);s.enter(self.entries[0])
        for i,pc in enumerate(READ_PC):s.read(pc,self.s['out']+8*i,8)
        for omitted in (0,32,33):
            s=self.setup()
            with self.assertRaises(ValueError):self.output(s,omitted);s.enter(self.entries[0])
        s=self.setup();self.output(s);s.enter(self.entries[0])
        for i,pc in enumerate(READ_PC[:-1]):s.read(pc,self.s['out']+8*i,8)
        with self.assertRaises(ValueError):s.read(READ_PC[-1],self.s['out']+264,4)
        with self.assertRaises(ValueError):s.finish()
    def test_actual_clone_all_three_seed_order(self):
        for call in (1365,3360,5355):
            s=self.fp_snapshot(call);self.feed_clone(s);self.output(s);s.enter(self.entries[25]);self.assertEqual(s.fp_stores,64)
    def test_equal_drop_swap_duplicate_and_missingVL0(self):
        self.assertEqual(self.rows[1365]['a'],self.rows[1366]['a'])
        for omit in (62,63):
            with self.assertRaises(ValueError):s=self.fp_snapshot(1366);self.feed_clone(s,omit=omit);self.output(s);s.enter(self.entries[25])
        for flag in ('swap','duplicate'):
            with self.assertRaises(ValueError):s=self.fp_snapshot(1366);self.feed_clone(s,**{flag:True})
        with self.assertRaises(ValueError):self.output(self.fp_snapshot(1365))
    def test_mask_upper_wrong_owner_and_stale_seed(self):
        s=self.initial()
        for _,pc,key,off,val in s.seed[:92]:s.store(pc,self.code[pc],self.s[key]+off,8,val)
        with self.assertRaises(ValueError):
            for i,(pc,off,w,val) in enumerate(mask_schedule(0)):s.store(pc,self.code[pc],self.s['mask']+off,w,1 if i==15 else val)
        s=self.fp_snapshot(3360);pc=int(FP_PATHS[0]['pcs'][0],16);s.enter(pc)
        with self.assertRaises(ValueError):
            for rawpc in FP_PATHS[0]['pcs'][1:]:s.enter(int(rawpc,16))
    def test_physical2_VI2_and_EOF(self):
        self.assertEqual(full_group({24:0,25:0},24),bytes(256))
        with self.assertRaises(ValueError):full_group({24:0},24)
        insn=self.h['op_19'][8]['insn']
        for vl in (1,2):self.assertFalse(target_required(dict(op=19,vl=vl,start=0),insn))
        self.assertTrue(target_required(dict(op=19,vl=3,start=0),insn))
        self.assertTrue(target_required(dict(op=24,vl=3,start=0),self.h['op_24'][8]['insn']))
        def complete():
            b=RawBoundary()
            for pc,insn,rest in BOOT:b.enter(pc,insn,rest)
            b.enter(0x80000000,0x00026197,'');b.success(0x8000007a,0x00a2b023,1);return b
        complete().finish()
        with self.assertRaises(ValueError):RawBoundary().finish()
        with self.assertRaises(ValueError):complete().enter(0x8000007e,0xa001,' mem 0x80000100 0x1')
        with self.assertRaises(ValueError):complete().enter(0x80000082,self.code[0x80000082],'')
if __name__=='__main__':unittest.main(verbosity=2)
