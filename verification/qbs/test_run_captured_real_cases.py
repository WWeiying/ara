import unittest

from qbs.run_captured_real_cases import parse_result


class CapturedRealCaseResultTests(unittest.TestCase):
    RESULT = (
        "case=q2k_ffn_down profile=Q2_K M=1 N=896 K=4864 "
        "checksum=1.25 max_abs=3.57627869e-7 mismatches=0/896"
    )

    def test_accepts_matching_zero_mismatch_result(self):
        result = parse_result(self.RESULT, "q2k_ffn_down", "q2_k", 896, 4864)
        self.assertEqual(result["outputs"], 896)
        self.assertEqual(result["mismatches"], 0)

    def test_rejects_wrong_shape_or_mismatch(self):
        with self.assertRaises(ValueError):
            parse_result(self.RESULT, "q2k_ffn_down", "q2_k", 896, 4096)
        with self.assertRaises(ValueError):
            parse_result(self.RESULT.replace("0/896", "1/896"),
                         "q2k_ffn_down", "q2_k", 896, 4864)

    def test_rejects_incomplete_or_multiple_results(self):
        with self.assertRaises(ValueError):
            parse_result("case=q2k_ffn_down", "q2k_ffn_down", "q2_k", 896, 4864)
        with self.assertRaises(ValueError):
            parse_result(self.RESULT + "\n" + self.RESULT,
                         "q2k_ffn_down", "q2_k", 896, 4864)


if __name__ == "__main__":
    unittest.main()
