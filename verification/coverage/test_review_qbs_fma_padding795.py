import unittest
from fractions import Fraction

import review_qbs_fma_padding795 as proof


class PaddingAndWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = proof.collect()

    def test_actual_typed_const_and_protected_complement(self):
        r = self.receipt
        self.assertEqual(r['constant_position_count'], 56)
        self.assertEqual(r['constant_source_bits'], [0, 1] + list(range(50, 76)))
        self.assertEqual(r['dynamic_product_missing_positions'], list(range(932, 938)))
        self.assertEqual(r['other_five_field_missing_positions_protected'], 208)
        self.assertFalse(r['native_qualified'])
        self.assertFalse(r['EL_created'])

    def test_wrong_precision_or_width_rejected(self):
        for precision, width in ((53, 163), (11, 37), (24, 77), (True, 76)):
            with self.assertRaises(ValueError):
                proof.padding_bits(precision, width)

    def test_slot_order_is_not_direction_order(self):
        positions = proof.pair_positions(928, proof.padding_bits(24, 76))
        self.assertEqual(set(positions), {p ^ 1 for p in positions})
        self.assertFalse(set(positions) & set(range(932, 1028)))

    def test_real_alignment_witness_not_constant(self):
        small, large = self.receipt['witnesses']
        self.assertEqual(small['addend_shamt'], 0)
        self.assertEqual(small['addend_sticky_bits'], 0)
        self.assertEqual(large['addend_shamt'], 76)
        self.assertEqual(large['addend_sticky_bits'], 0x1008)
        self.assertNotEqual(small['sum_sticky_bits'], large['sum_sticky_bits'])
        self.assertEqual(small['product_shifted'] & 0x1f, 0)
        self.assertEqual(large['product_shifted'] & 0x1f, 0)

    def test_model_rejects_foreign_domain(self):
        for words in ((0x7f800000, 0x41000000, 0),
                      (0x3f800000, 0x41000000, 0xc1000000),
                      (1 << 32, 0x41000000, 0)):
            with self.assertRaises(ValueError):
                proof.alignment(*words)

    def test_exact_rational_rounding_and_flags(self):
        self.assertEqual(proof.gold.round32(Fraction(2) ** -150), (0, 3))
        self.assertEqual(proof.gold.round32(Fraction(2) ** -149), (1, 0))
        self.assertEqual(proof.gold.round32(Fraction(1) + Fraction(2) ** -24),
                         (0x3f800000, 1))
        for row in self.receipt['full_descriptor_gold']:
            self.assertEqual(row['positive_result'], '0x410e3000')
            self.assertEqual(row['negative_result'], '0xc10e3000')
            self.assertEqual(row['fflags'], 3)


if __name__ == '__main__':
    unittest.main()
