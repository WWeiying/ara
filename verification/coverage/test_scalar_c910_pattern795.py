import copy
from fractions import Fraction
import json
from pathlib import Path
import unittest
import build_scalar_c910_pattern795 as b

PRE=b.life.OUT/'scalar-c910-pattern795-preflight-agent-20261008-02'


class IntegerGold(unittest.TestCase):
    def test_exact_div(self):
        e=b.gold(0x4018000000000000,0x4008000000000000,False,0)
        self.assertEqual((e['result'],e['fflags']),(0x4000000000000000,0))

    def test_third_nearest_and_directed(self):
        for rm,result in ((0,0x3fd5555555555555),(1,0x3fd5555555555555),
                (2,0x3fd5555555555555),(3,0x3fd5555555555556),(4,0x3fd5555555555555)):
            e=b.gold(0x3ff0000000000000,0x4008000000000000,False,rm)
            self.assertEqual((e['result'],e['fflags']),(result,1))

    def test_negative_directed(self):
        down=b.gold(0xbff0000000000000,0x4008000000000000,False,2)
        up=b.gold(0xbff0000000000000,0x4008000000000000,False,3)
        self.assertEqual(down['result'],0xbfd5555555555556)
        self.assertEqual(up['result'],0xbfd5555555555555)

    def test_sqrt_exact_and_irrational(self):
        self.assertEqual(b.gold(0x4010000000000000,0,True,0)['result'],0x4000000000000000)
        self.assertEqual(b.gold(0x4010000000000000,0,True,0)['fflags'],0)
        self.assertEqual(b.gold(0x4000000000000000,0,True,0)['result'],0x3ff6a09e667f3bcd)
        self.assertEqual(b.gold(0x4000000000000000,0,True,1)['result'],0x3ff6a09e667f3bcc)

    def test_sqrt_rounded_neighbors_bound_exact_square(self):
        for e in b.cells()[128:192]:
            low=b.gold(e['a'],e['b'],True,2)['result'];high=b.gold(e['a'],e['b'],True,3)['result']
            self.assertLessEqual(b.value(low)**2,b.value(e['a']))
            self.assertGreaterEqual(b.value(high)**2,b.value(e['a']))
            self.assertLessEqual(high-low,1)

    def test_ties_even_rmm_and_directed(self):
        self.assertEqual(b.increment(2,True,0,False,0),0)
        self.assertEqual(b.increment(3,True,0,False,0),1)
        self.assertEqual(b.increment(2,True,0,False,4),1)
        self.assertEqual(b.increment(2,True,-1,True,2),1)

    def test_invalid_rm_or_nonfinite_domain(self):
        for args in ((0x3ff0000000000000,0x3ff0000000000000,False,5),
                (0x7ff0000000000000,0x3ff0000000000000,False,0),
                (0x3ff0000000000000,0,False,0),(0xbff0000000000000,0,True,0)):
            with self.assertRaises(ValueError):b.gold(*args)

    def test_finite224_and_64_normal_selectors(self):
        cells=b.cells();self.assertEqual(len(cells),224)
        self.assertEqual(sum(e['sqrt'] for e in cells),64)
        self.assertEqual({64+((e['b']&b.MASK)>>46) for e in cells[:128]},set(range(64,128)))
        for e in cells:
            self.assertTrue(0<((e['result']>>52)&2047)<2047)
            self.assertIn(e['fflags'],(0,1));self.assertEqual(e['fcsr'],e['rm']<<5|e['fflags'])

    def test_header_is_exact_integer_gold(self):
        self.assertEqual(b.header().count('ul,'),3*224)
        self.assertIn('pattern_cells[224]',b.header())

    def test_source_typed90_and_frozen795(self):
        proof=b.source_evidence();self.assertTrue(proof['all64_DIV_selectors'])
        self.assertEqual(sum(map(len,proof['target']['coordinates'].values())),90)
        self.assertFalse(proof['measured_gain'])


class ActualSoftware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=json.loads((PRE/'preflight.json').read_text())

    def test_actual_spike_full_gold_reference(self):
        self.assertEqual(b.validate(b.build.parse_spike_commits(PRE/'spike.trace'),self.pre['symbols']),self.pre['counts'])
        b.life.check(self.pre['pins'])

    def test_actual_opcode_count_and_noC(self):
        rows=list(b.build.parse_spike_commits(PRE/'spike.trace'))
        self.assertEqual(sum(c.instruction==0x1a107153 for c in rows),160)
        self.assertEqual(sum(c.instruction==0x5a007153 for c in rows),64)
        self.assertTrue(all(c.instruction&3==3 for c in rows))

    def test_corrupt_reference_result_rejected(self):
        rows=list(b.build.parse_spike_commits(PRE/'spike.trace'))
        i=next(i for i,c in enumerate(rows) if c.pc==self.pre['symbols']['pattern_div_insn'])
        rows[i]=copy.deepcopy(rows[i]);rows[i].fpr_writes[2]^=1
        with self.assertRaises(ValueError):b.validate(rows,self.pre['symbols'])


if __name__=='__main__':unittest.main()
