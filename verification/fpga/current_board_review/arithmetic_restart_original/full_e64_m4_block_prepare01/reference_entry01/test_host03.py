"""Retain all 19 entry tests and discriminate final-instruction effect ordering."""
import unittest
from test_host import EntryTests,fixture,SPEC,S,C

def before_final_store(skip_last_read=False):
    obj=fixture(0);path=SPEC['mask_paths']['0']
    stores={e['pc']:e for e in path['events']}
    loads={e['load']:e for e in path['events'] if e['load'] is not None}
    last=path['events'][-1]
    assert path['pcs'][-1]==last['pc'] and last['width']==1
    for pc in path['pcs'][:-1]:
        obj.enter(pc,{})
        if pc in loads:
            e=loads[pc]
            if not (skip_last_read and pc==last['load']):
                obj.read(pc,S['mask']+e['offset'],1,e['previous'])
        if pc in stores:
            e=stores[pc];obj.store(pc,C[pc],S['mask']+e['offset'],e['width'],e['value'])
        obj.leave(pc,{})
    return obj,last

def final_store(obj,e,value=None):
    obj.store(e['pc'],C[e['pc']],S['mask']+e['offset'],1,e['value'] if value is None else value)

class PhaseOrderTests(unittest.TestCase):
    def test_enter_effect_leave_positive(self):
        obj,e=before_final_store();before=obj.mask_cursor
        obj.enter(e['pc'],{})
        self.assertEqual(obj.active,'mask');self.assertEqual(obj.mask_cursor,before)
        final_store(obj,e);self.assertEqual(obj.active,'mask')
        obj.leave(e['pc'],{})
        self.assertIsNone(obj.active);self.assertEqual(obj.mask_cursor,before+1)
    def test_missing_final_store_or_premature_leave(self):
        obj,e=before_final_store();obj.enter(e['pc'],{})
        with self.assertRaisesRegex(ValueError,'Full16SD'):obj.leave(e['pc'],{})
    def test_wrong_final_store_value(self):
        obj,e=before_final_store();obj.enter(e['pc'],{})
        with self.assertRaisesRegex(ValueError,'cumulative bitset'):final_store(obj,e,e['value']^1)
    def test_missing_final_LBU(self):
        obj,e=before_final_store(True);obj.enter(e['pc'],{})
        with self.assertRaisesRegex(ValueError,'preceding LBU'):final_store(obj,e)
    def test_missing_leave_before_next_instruction(self):
        obj,e=before_final_store();obj.enter(e['pc'],{});final_store(obj,e)
        with self.assertRaisesRegex(ValueError,'scalar phase'):obj.enter(SPEC['output_stores'][0],{})
    def test_duplicate_final_store(self):
        obj,e=before_final_store();obj.enter(e['pc'],{});final_store(obj,e)
        with self.assertRaisesRegex(ValueError,'mask owner'):final_store(obj,e)
    def test_wrong_closing_PC(self):
        obj,e=before_final_store();obj.enter(e['pc'],{});final_store(obj,e)
        with self.assertRaisesRegex(ValueError,'actual final'):obj.leave(e['pc']+2,{})

if __name__=='__main__':unittest.main(verbosity=2)
