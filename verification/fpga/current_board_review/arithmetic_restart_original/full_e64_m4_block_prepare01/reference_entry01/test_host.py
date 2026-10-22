"""Small observer negatives from source-qualified checkpoints, not DUT evidence."""
import unittest
from context import *
from lifecycle import Lifecycle,full_group
from raw_boundary import RawBoundary,BOOT
from reference_check import validate_console,validate_exit
S,C,H,ROWS=artifacts();SPEC=definition()
REG={name:n for n,name in enumerate('zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6'.split())}

def fixture(i):
    obj=Lifecycle(S,C,[H[f'op_{n}'][0]['pc'] for n in range(35)],ROWS,SPEC)
    # Explicit synthetic prior-call checkpoint for local event tests only.
    obj.boot_locked=obj.entered=True;obj.next_bss=S['__bss_end'];obj.calls=i
    obj.seed_cursor=184*(ROWS[i]['seed']+1);return obj

def feed_setup(obj,mutation=None):
    row=ROWS[obj.calls];regs={}
    if row['si']==0:
        path=SPEC['mask_paths'][str(row['mode'])];stores={e['pc']:e for e in path['events']};loads={e['load']:e for e in path['events'] if e['load'] is not None}
        for pc in path['pcs']:
            obj.enter(pc,regs)
            if pc in loads:
                e=loads[pc];obj.read(pc,S['mask']+e['offset'],1,e['previous'])
            if pc in stores:
                e=stores[pc]
                if mutation=='missing_mask_clear' and e['offset']==120 and e['width']==8:continue
                if mutation=='missing_mask_bit' and e['width']==1:continue
                obj.store(pc,C[pc],S['mask']+e['offset'],e['width'],e['value'])
            obj.leave(pc,regs)
    if row['op']>=25 and mutation!='cached_FP':
        path=SPEC['FP_paths'][str(row['seed'])];stores={e['pc']:e for e in path['stores']};loads={e['pc']:e for e in path['loads']}
        for pc in path['pcs']:
            obj.enter(pc,regs)
            asm=SPEC['asm'][str(pc)]
            if asm['op']=='ld' and asm['args']=='t3,144(sp)':
                value=row['seed'] if mutation!='cross_seed' else (row['seed']+1)%3
                obj.read(pc,S['__stack_top']-320+144,8,value)
            if pc in loads:
                i=loads[pc]['slot'];obj.read(pc,S['fp_inputs']+8*i,8,obj.fp_inputs[i])
            if pc in stores:
                e=stores[pc];i=e['index'];bank=e['bank']
                if mutation=='missing_FP' and i==63 and bank=='b':continue
                obj.store(pc,C[pc],S[bank]+8*i,8,row[bank][i])
            obj.leave(pc,regs)
    for i,pc in enumerate(SPEC['output_stores']):
        obj.enter(pc,regs);obj.store(pc,C[pc],S['out']+8*i,8,91)
    obj.enter(H[f"op_{row['op']}"][0]['pc'],regs)

def feed_compare(obj,mutation=None):
    row=ROWS[obj.calls-1];cmp=SPEC['comparator'];loads={e['pc']:e for e in cmp['loads']};ids={e['pc']:e for e in cmp['ids']};regs={}
    for pc in cmp['all_equal_pcs']:
        obj.enter(pc,regs);rd=None
        if pc==cmp['initial_zero']:
            value=1 if mutation=='stale_flag' else 0;rd=(15,value)
        if pc in ids:
            i=ids[pc]['block'];value=row['ids'][i]+(1 if mutation=='wrong_ID' and i==8 else 0)
            obj.read(pc,S['e64m4_block_ids']+18*(obj.calls-1)+2*i,2,value)
        if pc in loads:
            e=loads[pc];i=e['word'];actual=e['kind']=='actual'
            if mutation=='missing_actual' and actual and i==32:continue
            if mutation=='missing_expected' and not actual and i==65:continue
            address=S['out']+8*i if actual else S['e64m4_dictionary']+64*row['ids'][i//8]+8*(i%8)
            value=row['words'][i]
            if mutation=='wrong_expected_address' and not actual and i==65:address-=8
            if mutation=='wrong_expected_value' and not actual and i==0:value^=1
            if mutation=='rear_guard' and actual and i==65:value^=1<<63
            obj.read(pc,address,8,value)
            rd=(REG[SPEC['asm'][str(pc)]['args'].split(',')[0]],value)
        obj.effect(pc,rd)
        if rd:regs[rd[0]]=rd[1]
        obj.leave(pc,regs)

class EntryTests(unittest.TestCase):
    def test_actual_soc_and_reference_identity(self):
        soc=definition('soc')
        self.assertNotEqual(soc['elf_sha256'],SPEC['elf_sha256'])
        self.assertNotEqual(soc['comparator']['all_equal_pcs'][0],SPEC['comparator']['all_equal_pcs'][0])
        self.assertEqual(SPEC['helpers']['op_0'][0]['insn'],soc['helpers']['op_0'][0]['insn'])
        self.assertEqual(sha(SOFT/'spike/program.elf'),'42e53dc666391e88db7c2d436f7972cda362b575ca9e26806110841fecce51ae')
    def test_owned_positive_first_FP_nextseed_final(self):
        for i in (0,1365,3360,5984):
            obj=fixture(i);feed_setup(obj);feed_compare(obj)
            self.assertTrue(obj.completed_oracle);self.assertEqual((obj.read_cursor,obj.expected_cursor,obj.id_cursor),(66,66,9))
    def test_missing_actual(self):
        obj=fixture(0);feed_setup(obj)
        with self.assertRaises(ValueError):feed_compare(obj,'missing_actual')
    def test_missing_expected(self):
        obj=fixture(0);feed_setup(obj)
        with self.assertRaises(ValueError):feed_compare(obj,'missing_expected')
    def test_wrong_ID(self):
        obj=fixture(0);feed_setup(obj)
        with self.assertRaises(ValueError):feed_compare(obj,'wrong_ID')
    def test_wrong_expected_address(self):
        obj=fixture(0);feed_setup(obj)
        with self.assertRaises(ValueError):feed_compare(obj,'wrong_expected_address')
    def test_wrong_expected_value(self):
        obj=fixture(0);feed_setup(obj)
        with self.assertRaises(ValueError):feed_compare(obj,'wrong_expected_value')
    def test_rear_guard(self):
        obj=fixture(0);feed_setup(obj)
        with self.assertRaises(ValueError):feed_compare(obj,'rear_guard')
    def test_stale_flag(self):
        obj=fixture(0);feed_setup(obj)
        with self.assertRaises(ValueError):feed_compare(obj,'stale_flag')
    def test_missing_FP(self):
        with self.assertRaises(ValueError):feed_setup(fixture(1365),'missing_FP')
    def test_cross_seed(self):
        with self.assertRaises(ValueError):feed_setup(fixture(3360),'cross_seed')
    def test_cache_reuse(self):
        with self.assertRaises(ValueError):feed_setup(fixture(1365),'cached_FP')
    def test_mask_clear(self):
        with self.assertRaises(ValueError):feed_setup(fixture(0),'missing_mask_clear')
    def test_mask_selected(self):
        with self.assertRaises(ValueError):feed_setup(fixture(0),'missing_mask_bit')
    def test_partial_not_full(self):
        obj=fixture(0);feed_setup(obj);feed_compare(obj)
        with self.assertRaises(ValueError):obj.finish()
    def test_physical_four_groups(self):
        self.assertEqual(len(full_group({n:0 for n in range(8,12)},8)),512)
        with self.assertRaises(ValueError):full_group({8:0,9:0},8)
    def test_illegal_exit(self):
        validate_exit(0)
        for value in (1,77,None,False):
            with self.assertRaises(ValueError):validate_exit(value)
    def test_marker(self):
        marker='RVV_MATRIX_PASS sew=64 vlmax=64 cases=5985 elements=383040 errors=0 seeds=3 guard_tail_mask_vstart=checked\n'
        validate_console(marker)
        for text in (marker.replace('5985','4095'),marker.replace('vlmax=64','vlmax=32'),marker+'RVV_MATRIX_DETAIL bad\n',marker.replace('errors=0','errors=1'),''):
            with self.assertRaises(ValueError):validate_console(text)
    def test_actual_exit_and_EOF(self):
        obj=RawBoundary()
        for pc,insn,rest in BOOT:obj.enter(pc,insn,rest)
        obj.enter(0x80000000,0x297,'')
        with self.assertRaises(ValueError):obj.finish()
        with self.assertRaises(ValueError):obj.success(0x8000007a,0x00a2b023,0)
        obj.success(0x8000007a,0x00a2b023,1)
        obj.enter(0x8000007e,0xa001,'');obj.finish()
        with self.assertRaises(ValueError):obj.enter(0x8000007e,0xa001,'x1 0x1')

if __name__=='__main__':unittest.main(verbosity=2)
