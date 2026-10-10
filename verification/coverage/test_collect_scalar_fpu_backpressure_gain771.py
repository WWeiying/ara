import copy
import json
import unittest
import collect_scalar_fpu_backpressure_gain771 as g

class Tests(unittest.TestCase):
    def test_real_diag_contract(self):g.contract(g.life.read_bound(g.DIAG,g.DIAG_SHA))
    def test_mutated_diag(self):
        original=g.life.read_bound(g.DIAG,g.DIAG_SHA)
        for path,value in ((('contract','mmu_request_cycles'),1),(('backpressure','observed'),False),
                           (('scalar_counts','matched_instructions'),284)):
            q=copy.deepcopy(original);q[path[0]][path[1]]=value
            with self.assertRaises(ValueError):g.contract(q)
    def test_zero_gain_rejected(self):
        with self.assertRaises(ValueError):g.positive(dict(line=0,cond=0,branch=0,fsm=0),0)
        g.positive(dict(line=0,cond=0,branch=0,fsm=0),1)
    def test_exact_serialized_pairs(self):
        shape='<tgldef><tglshape><vectornode name="a" file="1" line_num="2" left="1" right="0"/><node name="b" file="1" line_num="3"/></tglshape></tgldef>'
        old=dict(width=6,checksum='1',bits='0x0');new=dict(old,bits='0x22')
        rows,arrays=g.pair_coordinates(shape,old,new)
        self.assertEqual([r['positions'] for r in rows],[[0],[4]]);self.assertEqual(arrays,[])
        with self.assertRaises(ValueError):g.pair_coordinates(shape,dict(old,width=7),dict(new,width=7))
        with self.assertRaises(ValueError):g.pair_coordinates(shape,old,dict(new,checksum='2'))

if __name__=='__main__':unittest.main()
