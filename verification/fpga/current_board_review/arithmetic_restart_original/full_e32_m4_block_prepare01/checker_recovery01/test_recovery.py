"""Small three-seed tests using actual linked paths, not a new reference run."""
import unittest
from context import artifacts,linked,width
from lifecycle import Lifecycle

ORDINALS=(1366,3361,5356)

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s,cls.code,cls.helpers,cls.rows=artifacts()
        cls.entries=[cls.helpers[f'op_{i}'][0]['pc'] for i in range(35)]
    def observer(self,seed,loads=True):
        q=Lifecycle(self.s,self.code,self.entries,self.rows)
        q.entered=q.boot_locked=True;q.calls=ORDINALS[seed]-1
        row=q.row();self.assertEqual((row['ordinal'],row['seed'],row['op'],row['vl'],row['start']),
            (ORDINALS[seed],seed,25,0,0))
        q.seed_cursor=368*(seed+1);q.read_cursor=65
        for e in q.mask[row['mode']]:self.feed(q,e)
        if loads:
            for e in q.fp[seed][:8]:self.feed(q,e)
        return q
    def feed(self,q,e):
        pc=int(e['pc'],16)
        if e['kind']=='FP':q.read(pc,e['address'],e['size'],e['value'])
        else:q.store(pc,self.code[pc],e['address'],e['size'],e['value'])
    def test_three_original_VL0_positives_through_last_b127_and_helper(self):
        for seed in range(3):
            with self.subTest(seed=seed):
                q=self.observer(seed)
                for e in q.fp[seed][8:]:self.feed(q,e)
                self.assertEqual(q.fp[seed][-1]['address'],self.s['b']+127*4)
                self.assertEqual((q.fp_reads,q.fp_stores,q.fp_cursor),(8,256,264))
                for e in q.init:self.feed(q,e)
                q.enter(self.entries[25]);self.assertEqual(q.calls,ORDINALS[seed])
    def test_union_classification_but_exact_current_path(self):
        for seed in range(3):
            for mutation in ('same_seed_other_PC','other_seed_PC','other_seed_path','bank','width','value'):
                with self.subTest(seed=seed,mutation=mutation):
                    q=self.observer(seed);e=dict(q.fp[seed][8])
                    if mutation=='same_seed_other_PC':e['pc']=q.fp[seed][9]['pc']
                    if mutation=='other_seed_PC':e['pc']=q.fp[(seed+1)%3][8]['pc']
                    if mutation=='other_seed_path':e=dict(q.fp[(seed+1)%3][8])
                    if mutation=='bank':e['address']=self.s['b']
                    if mutation=='width':e['size']=8
                    if mutation=='value':e['value']^=1
                    self.assertIn(int(e['pc'],16),q.fp_store_pcs)
                    with self.assertRaisesRegex(ValueError,'Exact linked source memory'):self.feed(q,e)
    def test_missing_equal_value_first_A_and_last_B(self):
        for seed in range(3):
            q=self.observer(seed);self.assertEqual(q.fp[seed][8]['value'],q.fp[seed][9]['value'])
            with self.assertRaises(ValueError):self.feed(q,q.fp[seed][9])
            q=self.observer(seed)
            for e in q.fp[seed][8:-1]:self.feed(q,e)
            with self.assertRaises(ValueError):self.feed(q,q.init[0])
    def test_duplicate_and_extra_SW(self):
        for seed in range(3):
            q=self.observer(seed);self.feed(q,q.fp[seed][8])
            with self.assertRaises(ValueError):self.feed(q,q.fp[seed][8])
            q=self.observer(seed)
            for e in q.fp[seed][8:]:self.feed(q,e)
            with self.assertRaises(ValueError):self.feed(q,q.fp[seed][-1])
    def test_load_classification_all_seeds_and_order(self):
        for seed in range(3):
            q=self.observer(seed,False)
            for e in q.fp[seed][:8]:
                self.assertEqual(e['size'],4);self.feed(q,e)
            self.assertEqual(q.fp_reads,8)
            for mutation in ('missing_first','wrong_PC','wrong_bank','width','value'):
                q=self.observer(seed,False);e=dict(q.fp[seed][0])
                if mutation=='missing_first':e=dict(q.fp[seed][1])
                if mutation=='wrong_PC':e['pc']=q.fp[seed][1]['pc']
                if mutation=='wrong_bank':e['address']=self.s['a']
                if mutation=='width':e['size']=8
                if mutation=='value':e['value']^=1
                if mutation=='wrong_bank':
                    # An unrelated read cannot advance the fresh-LW cursor.
                    self.feed(q,e);self.assertEqual(q.fp_cursor,0)
                    with self.assertRaises(ValueError):self.feed(q,q.fp[seed][8])
                else:
                    with self.assertRaises(ValueError):self.feed(q,e)
            q=self.observer(seed,False)
            for e in q.fp[seed][:7]:self.feed(q,e)
            with self.assertRaises(ValueError):self.feed(q,q.fp[seed][8])
    def test_seed_RNG_not_swallowed_by_FP_union(self):
        for seed in range(3):
            q=Lifecycle(self.s,self.code,self.entries,self.rows)
            q.entered=q.boot_locked=True;q.calls=seed*1995;q.seed_cursor=seed*368
            q.read_cursor=65 if seed else 0
            for _,pc,addr,size,value in q.seed[seed*368:(seed+1)*368]:
                self.assertNotIn(pc,q.fp_store_pcs);q.store(pc,self.code[pc],addr,size,value)
            self.assertEqual((q.seed_cursor,q.fp_stores,q.fp_reads),((seed+1)*368,0,0))
    def test_FP_PC_under_integer_seed_setup_is_rejected(self):
        q=Lifecycle(self.s,self.code,self.entries,self.rows);q.entered=True;q.seed_cursor=368
        with self.assertRaises(ValueError):self.feed(q,q.fp[0][8])

if __name__=='__main__':unittest.main()
