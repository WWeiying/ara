"""Small synthetic observer tests; not a second full source/reference run."""
import unittest
from context import *
from lifecycle import Lifecycle,REGS,full_group
from reference_check import exact_word,target_context,forbidden_pcs,RECORD
from raw_boundary import RawBoundary,BOOT

class EntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s,cls.code,cls.helpers,cls.rows=artifacts()
        cls.entries=[cls.helpers[f'op_{i}'][0]['pc'] for i in range(35)]
    def observer(self,index=0):
        q=Lifecycle(self.s,self.code,self.entries,self.rows)
        q.entered=q.boot_locked=True;q.calls=index;q.seed_cursor=368*(self.rows[index]['seed']+1)
        q.read_cursor=65 if index else 0
        return q
    def event(self,q,e):
        pc=int(e['pc'],16)
        if width(self.code[pc],True):q.store(pc,self.code[pc],e['address'],e['size'],e['value'])
        else:q.read(pc,e['address'],e['size'],e['value'])
    def cache(self,index=0,mutation=None):
        q=self.observer(index);q.calls=index+1;q.cache_calls=index;q.cache_complete=False;q.read_cursor=0
        plan=q.machine.walk(q.packed,self.s['e32m4_expected_ids']+18*index,self.rows[index]['gold'])
        branches={int(e['pc'],16):e for e in plan['branches']}
        events={int(e['pc'],16):e for e in plan['events']}
        changed=False
        for pc in plan['pcs']:
            regs={0:0,10:0};b=branches.get(pc);e=events.get(pc)
            if b:
                regs[REGS[b['left']]]=b['left_value'];regs[REGS[b['right']]]=b['right_value']
            if mutation=='tag' and b and b['taint']==['ID'] and not changed:
                regs[REGS[b['left']]]^=1;changed=True
            if mutation=='sticky' and b and b['taint']!=['ID'] and not changed:
                regs[10]=1;changed=True
            if mutation=='firstfill' and e and e['kind']=='GOLD' and not changed:
                changed=True;continue
            q.enter(pc,regs)
            if e:
                if not changed and ((mutation=='actual' and e['kind']=='OUT') or
                    (mutation=='expected' and e['kind']=='GOLD') or (mutation=='ID' and e['kind']=='ID')):
                    changed=True;continue
                value=e['value']
                if mutation=='tail' and e['kind']=='OUT' and e['address']==self.s['out']+512:value^=1<<32;changed=True
                q.read(pc,e['address'],e['size'],value)
        self.assertTrue(q.cache_complete);self.assertEqual(q.read_cursor,65)
        if mutation:self.assertTrue(changed)
        return q
    def test_actual_complete_cache_paths(self):
        index=max(range(len(self.rows)),key=lambda i:len(set(self.rows[i]['ids'])))
        for i in (0,index):
            q=self.cache(i);self.assertEqual(q.comparisons,65);self.assertEqual(q.id_reads,9)
            self.assertEqual(q.hits+q.misses,8)
    def test_cache_missing_or_changed_events(self):
        index=max(range(len(self.rows)),key=lambda i:len(set(self.rows[i]['ids'])))
        for mutation in ('actual','expected','ID','tag','sticky','firstfill','tail'):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.cache(index,mutation)
    def test_cache_reset_and_interior_owner(self):
        q=self.observer();pc=sorted(q.cache_pcs)[1]
        with self.assertRaises(ValueError):q.enter(pc,{0:0,10:0})
        q=self.cache()
        with self.assertRaises(ValueError):q.enter(q.cache_entry,{0:0,10:0})
    def test_FP_full_fresh_order(self):
        i=next(i for i,r in enumerate(self.rows) if r['op']==25)
        q=self.observer(i);r=self.rows[i];q.mask_cursor=len(q.mask[r['mode']])
        for e in q.fp[r['seed']]:self.event(q,e)
        self.assertEqual((q.fp_reads,q.fp_stores,q.fp_cursor),(8,256,264))
        for e in q.init:self.event(q,e)
        q.enter(self.entries[r['op']]);self.assertEqual(q.calls,i+1)
    def test_FP_omitted_same_value_write(self):
        i=next(i for i,r in enumerate(self.rows) if r['op']==25)
        q=self.observer(i);r=self.rows[i];q.mask_cursor=len(q.mask[r['mode']])
        # Omission is rejected by actual PC/address/order even if prior memory equals expected.
        for e in q.fp[r['seed']][:-1]:self.event(q,e)
        with self.assertRaises(ValueError):self.event(q,q.init[0])
    def test_mask_fullclear_then_cumulative_SB(self):
        q=self.observer()
        for e in q.mask[0]:self.event(q,e)
        self.assertEqual((q.mask_clear_stores,q.mask_bit_stores),(16,128))
        for e in q.init:self.event(q,e)
        q.enter(self.entries[0]);self.assertEqual(q.calls,1)
    def test_mask_middle_wrong_value_and_missing_clear(self):
        for omitted in (False,True):
            q=self.observer();events=q.mask[0]
            if omitted:
                for e in events[:15]:self.event(q,e)
                with self.assertRaises(ValueError):self.event(q,events[16])
            else:
                for e in events[:75]:self.event(q,e)
                e=dict(events[75]);e['value']^=1
                with self.assertRaises(ValueError):self.event(q,e)
    def test_output_all65_fresh_required(self):
        q=self.observer()
        for e in q.mask[0]:self.event(q,e)
        for e in q.init[:-1]:self.event(q,e)
        with self.assertRaises(ValueError):q.enter(self.entries[0])
    def test_target_empty_and_restart_context(self):
        r=next(r for r in self.rows if r['vl']==0)
        target_context(dict(vl=r['vl'],vtype=18,vstart=r['start']),r)
        for bad in (dict(vl=1,vtype=18,vstart=r['start']),dict(vl=0,vtype=18,vstart=r['start']+1),dict(vl=0,vtype=18)):
            with self.assertRaises(ValueError):target_context(bad,r)
    def test_full_physical4_not_low_group_only(self):
        self.assertEqual(len(full_group({i:0 for i in range(8,12)},8)),512)
        with self.assertRaises(ValueError):full_group({i:0 for i in range(8,11)},8)
    def test_tail_is_full_word_element127_and_guard(self):
        gold=self.rows[0]['gold'];v=int.from_bytes(gold[512:520],'little')
        exact_word(gold,512,8,v)
        for width_,value in ((4,v),(8,v^(1<<32)),(8,v^1)):
            with self.assertRaises(ValueError):exact_word(gold,512,width_,value)
    def test_all_disassembly_ELF_and_failure_interiors(self):
        f=linked()[0];bad=forbidden_pcs()
        for n in ('failure.part.0','trap_entry','replay_trap'):
            self.assertGreater(len(f[n]),1)
            self.assertTrue(all(x['pc'] in bad and self.code[x['pc']]==x['insn'] for x in f[n]))
        for space in (' ','\t',' \t '):
            m=RECORD.fullmatch(f'core{space}0:{space}3{space}0x80000000{space}(0x00000297)')
            self.assertIsNotNone(m)
    def test_marker_Builder_roundtrip(self):
        self.assertEqual(marker_encode(marker_decode(MARKER)),MARKER)
        with self.assertRaises(ValueError):marker_decode(MARKER.replace('766080','383040'))
        with self.assertRaises(ValueError):marker_encode(dict(marker_decode(MARKER),vlmax=64))
    def boundary(self):
        b=RawBoundary()
        for pc,insn,rest in BOOT:b.enter(pc,insn,rest)
        b.enter(0x80000000,self.code[0x80000000],'');return b
    def test_finite_EOF_pure_park(self):
        b=self.boundary();b.success(0x8000007a,self.code[0x8000007a],1)
        b.enter(0x8000007e,self.code[0x8000007e],'');b.finish()
        for pc,insn,rest in ((0x80000082,self.code[0x80000082],''),(0x8000007e,0xa001,' x1 0x1'),BOOT[0]):
            with self.assertRaises(ValueError):b.enter(pc,insn,rest)
    def test_nonzero_HTIF_and_premature_EOF(self):
        b=self.boundary()
        with self.assertRaises(ValueError):b.success(0x8000007a,self.code[0x8000007a],3)
        with self.assertRaises(ValueError):b.finish()

if __name__=='__main__':unittest.main()
