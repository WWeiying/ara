import copy
import unittest
from unittest.mock import patch
import collect_mask_compare_restart786 as c


class GateTests(unittest.TestCase):
    def test_actual_reference_full_prefix(self):
        pre=c.runner.preflight(); reference=c.reference_prefix(pre)
        self.assertEqual(len(reference),44559)

    def test_active_and_prestart_strict(self):
        for start in c.p.STARTS:
            gold=int.from_bytes(c.p.mask_gold(start),'little')
            c.mask_postimage(0,gold,start)
            with self.assertRaises(Exception): c.mask_postimage(0,gold^1,start)
            with self.assertRaises(Exception): c.mask_postimage(0,gold^(1<<start),start)

    def test_mask_tail_selector_not_spike_equality(self):
        gold=int.from_bytes(c.p.mask_gold(4),'little')
        c.mask_postimage(0,gold|(1<<1000),4)

    def test_tail_old_one_cannot_clear(self):
        gold=int.from_bytes(c.p.mask_gold(4),'little')
        with self.assertRaises(Exception): c.mask_postimage(1<<1000,gold,4)

    def test_unknown_full_postimage_rejected(self):
        with self.assertRaises(Exception): c.mask_postimage(0,None,4)

    def test_actual786_sequential_binding(self):
        q=c.runner.preflight(); a,bits,before,targets,pins=c.runner.baseline(q)
        self.assertEqual(len(bits['tests']),786); self.assertEqual(len(before),4)
        self.assertEqual(len(targets),8)

    def rows(self):
        a=dict(event='alloc',arch_seq='7',insn='010400d7',vl='64',vstart='4',eew='0',vd='1',use_vd='1',
               nr_lanes='4',vlen_bits='1024',vid='2',cycle='100')
        return [a,dict(a,event='done',cycle='101')]

    def test_context_exact(self):
        c.request_context(self.rows(),7,0x010400d7,64,4,1,True)

    def test_context_mutations(self):
        for key,value in [('vl','63'),('vstart','0'),('eew','1'),('vd','0'),('use_vd','0'),('vid','3'),('insn','0')]:
            rows=self.rows(); rows[1][key]=value
            with self.assertRaises(Exception): c.request_context(rows,7,0x010400d7,64,4,1,True)

    def test_duplicate_context(self):
        rows=self.rows(); rows.append(dict(rows[0]))
        with self.assertRaises(Exception): c.request_context(rows,7,0x010400d7,64,4,1,True)

    def test_missing_context(self):
        with self.assertRaises(Exception): c.request_context(self.rows()[:1],7,0x010400d7,64,4,1,True)

    def test_store_context_exact(self):
        rows=self.rows()
        for row in rows: row.update(vl='8',vstart='0',vd='0',use_vd='0',insn='02008027')
        c.request_context(rows,7,0x02008027,8,0,0,False)

    def test_terminal_missing_is_not_pass(self):
        with self.assertRaises(Exception): c.terminal(c.life.OUT/'nonexistent-mask-test',{})

    def test_no_backend_rejected(self):
        with self.assertRaises(Exception): c.native_state([],{}, {}, {},[])

    def test_budget_bound(self):
        self.assertEqual(c.runner.BUDGET,180)
        self.assertIn('+NO_FSDB',c.runner.command(c.life.OUT/'unused'))


if __name__=='__main__': unittest.main()
