import unittest
from fractions import Fraction
from unittest.mock import patch
import preflight_fclass_divsqrt783 as p


class FiniteGold(unittest.TestCase):
    def test_actual_frozen_shuffle_owners(self):
        text = (p.APP.parents[4] / 'hardware/include/ara_pkg.sv').read_text()
        for w in (16, 32, 64):
            self.assertEqual({p.physical_element(w, l, s, text) for l in range(4) for s in range(64 // w)}, set(range(256 // w)))
        self.assertEqual(p.physical_element(16, 0, 1, text), 8)
        self.assertEqual(p.physical_element(16, 0, 2, text), 4)
        with self.assertRaises(ValueError): p.physical_element(16, 0, 4, text)
        with self.assertRaises(ValueError): p.physical_element(16, 0, 0, text.replace('idx[00] = 00;', 'idx[00] = 01;'))

    def test_all_ten_classes_on_every_physical_element(self):
        for w in (16, 32, 64):
            for e in range(256 // w):
                self.assertEqual({p.gold(w, phase, e) for phase in range(10)}, {(1 << b, 0) for b in range(10)})

    def test_only_valid_rounding_modes(self):
        self.assertEqual({p.inputs(64, phase, 0)[1] for phase in range(25)}, set(range(5)))
        for rm in (-1, 5, 6, 7, True):
            with self.assertRaises(ValueError): p.rounded(Fraction(1, 2), 64, rm)

    def test_finite_div_inputs_and_signs(self):
        for w in (16, 32, 64):
            for phase in range(10, 20):
                for e in range(256 // w):
                    _, _, a, b = p.inputs(w, phase, e)
                    self.assertIn(p.value(b, w), (2, 4))
                    p.value(a, w)
            for e in range(256 // w):
                self.assertNotEqual(p.inputs(w, 10, e)[2] >> (w - 1), p.inputs(w, 11, e)[2] >> (w - 1))

    def test_underflow_after_rounding_boundary(self):
        f, bias = p.encoding(16)
        x = p.value((2 << f) - 1, 16) / 2
        self.assertEqual(p.rounded(x, 16, 0), (1 << f, 1))
        self.assertEqual(p.rounded(x, 16, 1), ((1 << f) - 1, 3))

    def test_exact_subnormal_has_no_underflow(self):
        self.assertEqual(p.rounded(p.value(0x400, 16) / 2, 16, 0), (0x200, 0))

    def test_sqrt_two_independent_bits(self):
        for w, nearest in ((16, 0x3da8), (32, 0x3fb504f3), (64, 0x3ff6a09e667f3bcd)):
            self.assertEqual(p.rounded(Fraction(2), w, 0, square=True), (nearest, 1))

    def test_smallest_subnormal_sqrt(self):
        for w, bits, flags in ((16, 0xc00, 0), (32, 0x1a3504f3, 1), (64, 0x1e60000000000000, 0)):
            self.assertEqual(p.rounded(p.value(1, w), w, 0, square=True), (bits, flags))

    def test_negative_sqrt_is_canonical_nv(self):
        for w in (16, 32, 64):
            f, bias = p.encoding(w)
            self.assertEqual(p.gold(w, 20, 2), (((2 * bias + 1) << f) | (1 << (f - 1)), 16))

    def test_exact_square(self):
        for w in (16, 32, 64):
            f, bias = p.encoding(w)
            self.assertEqual(p.gold(w, 20, 3), ((bias + 1) << f, 0))

    def test_all_images_have_exact_32bytes(self):
        for w in (16, 32, 64):
            for phase in range(25):
                aa, bb, dst, flags = p.images(w, phase)
                self.assertEqual([len(aa), len(bb), len(dst)], [32, 32, 32])
                self.assertFalse(flags & ~31)

    def test_class_padding_is_not_a_target(self):
        params = dict(OpGroup=2, FpFormat=2, EnableVectors=1, TrueSIMDClass=1, Width=64, SIMD_WIDTH=16, NUM_LANES=4)
        b = p.dynamic_class_bits(params)
        self.assertEqual(len(b), 40)
        self.assertFalse(b.intersection({16 * lane + bit for lane in range(4) for bit in range(10, 16)}))
        for key, value in (('FpFormat', 4), ('TrueSIMDClass', 0), ('EnableVectors', 0), ('OpGroup', 1)):
            with self.assertRaises(ValueError): p.dynamic_class_bits(dict(params, **{key: value}))

    def test_unknown_formats_and_phases_rejected(self):
        for w in (8, 128, True):
            with self.assertRaises(ValueError): p.encoding(w)
        for phase in (-1, 25, True):
            with self.assertRaises(ValueError): p.inputs(16, phase, 0)

    def test_encoded_unary_and_div_rules(self):
        prefix = '80002000:  v'
        with self.assertRaises(ValueError): p.linked(prefix)

    def test_empty_trace_rejected(self):
        symbols = {s: i for i, s in enumerate(p.SYMBOLS)}
        with patch.object(p.build, 'parse_spike_commits', return_value=[]):
            with patch.object(p.Path, 'read_text', return_value=''):
                with self.assertRaises(ValueError): p.validate(p.Path('/unused'), symbols)


if __name__ == '__main__': unittest.main()
