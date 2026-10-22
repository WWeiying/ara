import unittest
import prove_c910_lfn776 as proof


class LfnSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (proof.ROOT / 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_pack.v').read_text()

    def test_actual_source(self): self.assertEqual(len(proof.source_guard(self.source)), 5)
    def test_literal_mutation(self):
        with self.assertRaises(ValueError): proof.source_guard(self.source.replace("11'h7fe", "11'h7ff"))
    def test_sign_mutation(self):
        with self.assertRaises(ValueError): proof.source_guard(self.source.replace('{vfdsu_ex4_result_sign,11\'h7fe', "{1'b0,11'h7fe"))
    def test_mux_mutation(self):
        with self.assertRaises(ValueError): proof.source_guard(self.source.replace('? ex4_doub_lfn[63:0]', '? ex4_sing_lfn[63:0]'))
    def test_paired_difference(self):
        result, old, hold = proof.old_el_difference(7, [('0to1', {0}, 'logic'), ('1to0', {0}, 'logic')])
        self.assertEqual((result, old, hold), ([1, 2], [0], []))
    def test_single_direction_held(self):
        self.assertEqual(proof.old_el_difference(7, [('0to1', {0}, 'logic')]), ([1, 2], [], [0]))
    def test_whole_old_field(self): self.assertEqual(proof.old_el_difference(7, [(None, None, 'logic')])[0], [])
    def test_foreign_bit_rejected(self):
        with self.assertRaises(ValueError): proof.old_el_difference(7, [(None, {64}, 'logic')])


if __name__ == '__main__': unittest.main()
