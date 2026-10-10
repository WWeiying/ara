"""Independent scalar DIV/SQRT finite gold, exact source shape and launch boundaries."""
from fractions import Fraction
import unittest
import scalar_divsqrt_oracle as oracle
import run_scalar_divsqrt_finite as run


class FiniteScalar(unittest.TestCase):
    def test_exact20_known_results(self):
        rows=oracle.cases()
        self.assertEqual(len(rows),20)
        self.assertEqual([r['result'] for r in rows[:10]],[0x40400000,0x3eaaaaab,0x3eaaaaab,
            0x00400000,0,0x7f800000,0x40000000,0x3fb504f3,0x3fb504f4,0x20000000])
        self.assertEqual([r['result'] for r in rows[10:]],[0x4008000000000000,0x3fd5555555555555,
            0x3fd5555555555556,0x0008000000000000,0,0x7ff0000000000000,
            0x4000000000000000,0x3ff6a09e667f3bcd,0x3ff6a09e667f3bcd,0x2000000000000000])
        self.assertEqual([r['flags'] for r in rows],[0,1,1,0,3,5,0,1,1,0]*2)

    def test_integer_root_exact_and_halfway_even(self):
        for width,frac in ((32,23),(64,52)):
            self.assertEqual(oracle.sqrt_round(Fraction(4),width,'rne'),
                (0x40000000 if width==32 else 0x4000000000000000,0))
            # Squared exact midpoint around one: ties must round to even, not approximate sqrt.
            midpoint=(Fraction(1)+oracle.finite.pow2(-frac-1))**2
            one=0x3f800000 if width==32 else 0x3ff0000000000000
            self.assertEqual(oracle.sqrt_round(midpoint,width,'rne'),(one,1))
            self.assertEqual(oracle.sqrt_round(midpoint,width,'rup'),(one+1,1))

    def test_second_halfway_odd(self):
        value=(Fraction(1)+3*oracle.finite.pow2(-24))**2
        self.assertEqual(oracle.sqrt_round(value,32,'rne'),(0x3f800002,1))

    def test_input_mutation_changes_gold(self):
        row=oracle.cases()[7]
        self.assertNotEqual(oracle.evaluate(dict(row,a=0x40800000)),(row['result'],row['flags']))

    def test_nonfinite_zero_invalid_reject(self):
        for bits in (0x7f800000,0x7fc00000):
            with self.assertRaises(ValueError):oracle.evaluate(dict(oracle.cases()[0],a=bits))
        with self.assertRaises(ValueError):oracle.evaluate(dict(oracle.cases()[0],b=0))
        for value in (Fraction(0),Fraction(-1)):
            with self.assertRaises(ValueError):oracle.sqrt_round(value,32,'rne')

    def test_static_opcode_fprs_format_rounding(self):
        for row in oracle.cases():
            word=0x53|(3<<7)|(int(row['rounding']=='rup')*3<<12)|(int(row['width']==64)<<25)
            word|=(3<<27)|(1<<20) if row['operation']=='div' else 11<<27
            run.instruction(row,word)
            for bit in (7,15,20,25,12,27):
                with self.assertRaises(ValueError):run.instruction(row,word^(1<<bit))

    def test_nanbox_generated_all_f32_inputs(self):
        text=oracle.header(oracle.cases())
        self.assertEqual(text.count('0xffffffff'),30)

    def test_app_exact_operations_no_custom_vector(self):
        text=run.APP.read_text()
        self.assertEqual(text.count('  EVAL('),20)
        self.assertEqual(text.count('"fdiv.'),12)
        self.assertEqual(text.count('"fsqrt.'),8)
        self.assertNotIn('ecall',text);self.assertNotIn('vset',text)

    def test_frozen_command_isolation(self):
        cmd=run.command(run.PRE/'input.elf')
        self.assertIn('+NO_FSDB',cmd)
        self.assertIn('+COMMIT_TRACE='+str(run.RUN/'commit_trace.csv'),cmd)
        self.assertIn('+VECTOR_TRACE='+str(run.RUN/'vector_trace.csv'),cmd)
        self.assertEqual(cmd.count('-cm'),1)
        self.assertFalse(any(str(run.base.RUN) in x for x in cmd))
        self.assertFalse(any('force' in x or 'ucli' in x for x in cmd))

    def test_actual_compiled_single_scalar_rule158(self):
        book=run.life.read_bound(run.old.BUILD/'build-source-pins.json',run.old.SOURCE_SHA)
        pins={k:v for k,v in book.items() if k.endswith(('/ct_vfdsu_srt_radix16_with_sqrt.v','/fpnew_divsqrt_th_64_multi.sv'))}
        _,review=run.source_review(pins,book)
        self.assertEqual(review['physical_scalar_instances'],1)
        self.assertEqual(review['objects'],158)
        self.assertEqual(review['protected_objects'],52)
        self.assertTrue(review['upstream_bytes_equal'])
        self.assertFalse(review['vector_architecture_borrowed'])
        self.assertFalse(review['native_approval'])
        self.assertTrue(all(n['portnode']=='0' for n in review['signals']))


if __name__=='__main__':unittest.main()
