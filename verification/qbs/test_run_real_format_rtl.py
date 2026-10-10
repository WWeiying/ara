import unittest

from qbs.run_real_format_rtl import case_result


class RealFormatRtlLogTests(unittest.TestCase):
    LOG = (
        "QBS end-to-end case 0 PASS profile=3 M=1 N=16 "
        "Kb=48 layouts=2/1 cycles=2916\n"
        "QBS engine PASS: 1 functional cases\n"
    )

    def test_accepts_exact_profile_and_shape(self):
        self.assertEqual(case_result(self.LOG, 3, 48), 2916)

    def test_rejects_wrong_profile_or_k(self):
        with self.assertRaises(ValueError):
            case_result(self.LOG, 8, 48)
        with self.assertRaises(ValueError):
            case_result(self.LOG, 3, 28)

    def test_rejects_duplicate_or_error(self):
        with self.assertRaises(ValueError):
            case_result(self.LOG + self.LOG, 3, 48)
        with self.assertRaises(ValueError):
            case_result(self.LOG + "Error: bad output\n", 3, 48)


if __name__ == "__main__":
    unittest.main()
