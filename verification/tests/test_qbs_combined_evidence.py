import unittest

from qbs.check_combined_real_evidence import audit


GOOD = [
    "QBS_REAL_BENCH case=shape_decode_n32_qbs result=PASS mismatches=0 qbs_status=0",
    "LLAMA_OPERATOR operator/decode/attention_core PASS cycles=900 mismatches=0",
    "ATTENTION_DISPATCH native_v2=1 portable=0",
    "QBS_AKV_COMBINED result=PASS qbs_status=0 attention_status=0 attention_mode=akv_v2",
    "[QBS_PERF] seq=1 success=1 fault=0",
    "[AKV_PERF] seq=1 success=1 fault=0 v2_full=1 v2_column_load=0",
    "[AKV_PERF] seq=2 success=1 fault=0 v2_full=0 v2_column_load=1",
]


class CombinedEvidenceTests(unittest.TestCase):
    def test_complete_real_dut_evidence_passes(self):
        result = audit(GOOD)
        self.assertEqual(result["status"], "PASS", result["issues"])

    def test_missing_hardware_activity_or_bad_golden_fails(self):
        for records in (
            GOOD[:4] + GOOD[5:],
            GOOD[:-1] + [GOOD[-1].replace("v2_column_load=1", "v2_column_load=0")],
            [GOOD[0].replace("mismatches=0", "mismatches=1"), *GOOD[1:]],
            [GOOD[0], GOOD[1].replace("PASS", "FAIL"), *GOOD[2:]],
            [*GOOD, GOOD[-1]],
            GOOD[:-1] + [GOOD[-1].replace("seq=2", "seq=3")],
        ):
            with self.subTest(records=records):
                self.assertEqual(audit(records)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
