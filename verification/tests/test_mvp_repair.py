"""Independent fixed anchors for the bounded repair oracle."""
from pathlib import Path
import sys
import unittest

FPU = Path(__file__).resolve().parents[1] / "fpu"
sys.path.insert(0, str(FPU))
import run_mvp_repair as repair


class RepairOracleTest(unittest.TestCase):
    def test_exact(self):
        for rm in range(5):
            self.assertEqual(repair.oracle(0x3ff0000000000000, 0x3ff0000000000000, 64, rm),
                             (0x3ff0000000000000, 0))

    def test_inexact(self):
        self.assertEqual(repair.oracle(0xffffffff3f800000, 0xffffffff40400000, 32, 0),
                         (0xffffffff3eaaaaab, 1))
        self.assertEqual(repair.oracle(0xffffffff3f800000, 0xffffffff40400000, 32, 1),
                         (0xffffffff3eaaaaaa, 1))

    def test_overflow(self):
        self.assertEqual(repair.oracle(0x7fefffffffffffff, 0x3fe0000000000000, 64, 3),
                         (0x7ff0000000000000, 5))
        self.assertEqual(repair.oracle(0xffefffffffffffff, 0x3fe0000000000000, 64, 1),
                         (0xffefffffffffffff, 5))

    def test_sqrt_anchors(self):
        cases = repair.sqrt_cases()
        sqrt_two = next(c for c in cases if c["name"] == "sqrt_fp64_pow1_mant0_rm0")
        self.assertEqual(sqrt_two["expected_result"], "3ff6a09e667f3bcd")
        self.assertEqual(sqrt_two["expected_flags"], "01")
        sqrt_nine = next(c for c in cases if c["name"] == "sqrt_fp64_pow3_mant562949953421312_rm0")
        self.assertEqual(sqrt_nine["expected_result"], "4008000000000000")
        self.assertEqual(sqrt_nine["expected_flags"], "00")


if __name__ == "__main__":
    unittest.main()
