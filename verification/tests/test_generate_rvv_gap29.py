import random
import struct
import unittest
import generate_rvv_gap29 as g

class OracleTests(unittest.TestCase):
    def test_rne_host_half(self):
        rng = random.Random(29)
        for bits in g.fp_inputs() + [rng.getrandbits(32) for _ in range(10000)]:
            if bits & 0x7f800000 == 0x7f800000:
                continue
            value = struct.unpack('>f', struct.pack('>I', bits))[0]
            try:
                expected = int.from_bytes(struct.pack('>e', value), 'big')
            except OverflowError:
                expected = (bits >> 16 & 0x8000) | 0x7c00
            self.assertEqual(g.narrow_half(bits, 0)[0], expected)

    def test_exact_widen(self):
        for half in range(65536):
            if half & 0x7c00 == 0x7c00 and half & 1023:
                continue
            value = struct.unpack('>e', half.to_bytes(2, 'big'))[0]
            expected = int.from_bytes(struct.pack('>f', value), 'big')
            self.assertEqual(g.widen_half(half), expected)

    def test_flags_rounding(self):
        for rm, expected in ((0, 0x3c00), (1, 0x3c00), (2, 0x3c00),
                             (3, 0x3c01), (4, 0x3c01), (6, 0x3c01)):
            self.assertEqual(g.narrow_half(0x3f801000, rm), (expected, 1))
        self.assertEqual(g.narrow_half(0x33000000, 0), (0, 3))
        self.assertEqual(g.narrow_half(0x7f800001, 0), (0x7e00, 16))
        self.assertEqual(g.narrow_half(0x47800000, 1), (0x7bff, 5))

    def test_selection(self):
        self.assertEqual(len(g.cases()), 6)
        self.assertEqual(len(set(g.render(c) for c in g.cases())), 6)
        self.assertTrue(all(c[1] == 0 and c[3] == 4 for c in g.cases()))

if __name__ == '__main__':
    unittest.main()
