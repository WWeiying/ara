import csv
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import review_cast_numeric745 as review


class CastReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        book = __import__('json').loads((review.BASE/'combined-bits.json').read_bytes())
        cls.case = review.reference.cases()[1]
        db = next(p for p in book['tests'] if '/rvv_'+cls.case[0]+'/work/code.vdb' in p)
        cls.test = Path(db).parents[1]
        with (cls.test/'commit_trace.csv').open() as f:
            cls.rows = list(csv.DictReader(f))

    def mutated(self, predicate, mutate):
        rows = [dict(r) for r in self.rows]
        chosen = [r for r in rows if r['event']=='retire' and predicate(r)]
        self.assertTrue(chosen)
        mutate(chosen[0])
        self.assertEqual(sum(a!=b for a,b in zip(rows,self.rows)), 1)
        with patch.object(review.csv, 'DictReader', return_value=iter(rows)):
            with self.assertRaises(ValueError): review.actual_case(self.case,self.test,{})

    def test_actual_rtz_full_readback_flags(self):
        result = review.actual_case(self.case,self.test,{})
        self.assertEqual((result['phases'],result['readback_bytes'],result['conversions']), (6,2340,12))

    def test_wrong_flags_rejected(self):
        self.mutated(lambda r: int(r['insn'],16)&127==115 and int(r['insn'],16)>>20==1
                     and int(r['insn'],16)>>12&7==2,
                     lambda r:r.update(rd_wdata='%016x'%(int(r['rd_wdata'],16)^1)))

    def test_wrong_retired_opcode_rejected(self):
        self.mutated(lambda r:int(r['insn'],16)==0x488a1857,
                     lambda r:r.update(insn='488a9857'))

    def test_trap_rejected(self):
        self.mutated(lambda r:int(r['insn'],16)==0x488a1857,
                     lambda r:r.update(trap='1'))

    def test_interfaces_modified_round_flags_protected(self):
        for name in ('operands_i','input_sign_q','rnd_mode_q','negative_int_boundary',
                     'denorm_shamt','of_before_round','rounded_abs','int_result','status_d',
                     'mid_pipe_valid_q','out_pipe_result_q','mask_i','flush_i','result_o'):
            self.assertFalse(review.selected(ET.Element('node', name=name,portnode='0',line_num='100')))
        self.assertFalse(review.selected(ET.Element('node',name='input_mant',portnode='2',line_num='267')))
        self.assertFalse(review.selected(ET.Element('node',name='input_mant',portnode='0',line_num='424')))

    def test_complete_object_selection_no_hit_dependency(self):
        for value in ('0','1'):
            self.assertTrue(review.selected(ET.Element('vectornode',name='input_mant',
                               portnode='0',line_num='267',bits=value)))


if __name__=='__main__':unittest.main()
