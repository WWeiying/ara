import copy
from fractions import Fraction
import unittest
import scalar_fpu_finite_oracle as o
import run_scalar_fpu_finite as r


class FiniteQualification(unittest.TestCase):
    def test_exact20_flags(self):
        rows=o.cases()
        self.assertEqual(len(rows),20)
        self.assertEqual([x['index'] for x in rows],list(range(20)))
        self.assertEqual([x['flags'] for x in rows],[1,0,1,1,0,3,3,5,0,0]*2)

    def test_known_independent_results(self):
        rows=o.cases()
        self.assertEqual([x['result'] for x in rows[:10]],
            [0x3f800000,0xa8800000,0x3f800000,0x3f800001,0x00400000,0,0x80000000,
             0x7f800000,0x7f7fffff,0x41600000])
        self.assertEqual([x['result'] for x in rows[10:]],
            [0x3ff0000000000000,0xb970000000000000,0x3ff0000000000000,0x3ff0000000000001,
             0x0008000000000000,0,0x8000000000000000,0x7ff0000000000000,
             0x7fefffffffffffff,0x402c000000000000])

    def test_fused_not_two_roundings(self):
        for index in (1,11):
            row=o.cases()[index]
            a,b,c=(o.decode(row[k],row['width']) for k in ('a','b','c'))
            product,_=o.rounded(a*b,row['width'],'rne')
            separate=o.rounded(o.decode(product,row['width'])+c,row['width'],'rne')
            self.assertEqual(separate,(0,0))
            self.assertNotEqual(separate,o.evaluate(row))

    def test_changed_fma_operand_detectable(self):
        case=copy.deepcopy(o.cases()[1]);case['c']=0
        self.assertNotEqual(o.evaluate(case),(o.cases()[1]['result'],o.cases()[1]['flags']))

    def test_tiny_after_exact_no_uf(self):
        self.assertEqual(o.rounded(Fraction(1,1<<127),32,'rne'),(0x400000,0))
        self.assertEqual(o.rounded(Fraction(1,1<<150),32,'rne'),(0,3))

    def test_illegal_inputs_modes_rejected(self):
        for bits,width in ((0x7f800000,32),(0x7ff0000000000000,64),(1,16),(-1,32)):
            with self.assertRaises(ValueError):o.decode(bits,width)
        with self.assertRaises(ValueError):o.rounded(Fraction(1),32,'dynamic')

    def test_scalar_opcode_format_rm_register_guards(self):
        for row in o.cases():
            word=(2<<27 if row['operation']=='fma' else (2<<27 if row['operation']=='mul' else 0))
            word|=(int(row['width']==64)<<25)|(1<<20)|(3<<7)|(3<<12 if row['rounding']=='rup' else 0)
            word|=0x43 if row['operation']=='fma' else 0x53
            r.instruction(row,word)
            for changed in (word^(1<<25),word^(1<<12),word^(1<<7),word^0x10):
                with self.assertRaises(ValueError):r.instruction(row,changed)

    def test_exact_app_instruction_count(self):
        text=r.APP.read_text()
        self.assertEqual(text.count('  EVAL('),20)
        self.assertIn('guards != 35',text)
        self.assertNotIn('ecall',text)
        self.assertNotIn('vset',text)

    def test_header_nanbox_and_all_bits(self):
        rows=o.cases(); text=o.header(rows)
        self.assertEqual(text.count('  {'),20)
        self.assertIn('0xffffffff3f800001ul',text)
        self.assertEqual(r.boxed(rows[5]),0xffffffff00000000)
        self.assertEqual(r.boxed(rows[16]),0x8000000000000000)

    def test_frozen_one_shot_command(self):
        command=r.command(r.PRE/'input.elf')
        self.assertIn('+NO_FSDB',command)
        self.assertIn('+COMMIT_TOHOST=80001000',command)
        self.assertNotIn('-ucli',command)
        self.assertEqual(command.count('-cm'),1)


if __name__=='__main__':unittest.main()
