import unittest
from ordered_reference import OrderedReference


class OrderedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = OrderedReference()

    def test_exact_pv(self):
        result = self.ref.pv([[0x3f800000, 0x3f800000]], [0x3f800000], [[0]], [[0x3c00], [0x4000]])
        self.assertEqual((result["output"], result["fflags"]), ([[0x4200]], 0))

    def test_no_zero_coefficient_skip(self):
        result = self.ref.pv([[0]], [0x3f800000], [[0]], [[0x7c00]])
        self.assertEqual((result["output"], result["fflags"]), ([[0x7e00]], 16))

    def test_no_reassociation(self):
        result = self.ref.pv([[0x3f800000]*3], [0x3f800000], [[0]], [[0x6800], [0x3c00], [0xe800]])
        self.assertEqual((result["output"], result["fflags"]), ([[0]], 1))

    def test_old_scale_multiply_is_separate(self):
        result = self.ref.pv([[0x3f800000]], [0x40000000], [[0x7bff]], [[0xfbff]])
        self.assertEqual((result["output"], result["fflags"]), ([[0x7c00]], 5))

    def test_fma_is_fused(self):
        result = self.ref.pv([[0x3f802000]], [0x3f800000], [[0xbc00]], [[0x3bfe]])
        self.assertEqual((result["output"], result["fflags"]), ([[0x8010]], 0))

    def test_directed_rounding_and_underflow(self):
        args = ([[0x3f000000]], [0x3f800000], [[0]], [[1]])
        rne, rup = self.ref.pv(*args, rm=0), self.ref.pv(*args, rm=3)
        self.assertEqual((rne["output"], rne["fflags"]), ([[0]], 3))
        self.assertEqual((rup["output"], rup["fflags"]), ([[1]], 3))

    def test_widened_qk(self):
        result = self.ref.qk([[0x3c00, 0x4200]], [[0x4000, 0x4400]])
        self.assertEqual(result, dict(output=[[0x41600000]], fflags=0))

    def test_rejects_reserved_mode_or_shape(self):
        with self.assertRaises(ValueError):
            self.ref.qk([[0]], [[0]], rm=5)
        with self.assertRaises(ValueError):
            self.ref.pv([[0]], [0], [[0, 0]], [[0]])


if __name__ == "__main__":
    unittest.main()
