import unittest

from audit_uvm_no_traffic_719 import classify, parse_log, vector_data, FRONT, SCALAR


class AuditTests(unittest.TestCase):
    def test_correct_uvm_boundary(self):
        text = "UVM_ERROR : 2\n[VID/NO_TRAFFIC] 1\nUVM_ERROR file.sv(630) @ 1: top [VID/NO_TRAFFIC] missing\n"
        parsed = parse_log(text)
        self.assertEqual(len(parsed["errors"]), 1)
        self.assertEqual(parsed["errors"][0]["tag"], "VID/NO_TRAFFIC")
        self.assertEqual(parsed["summary_lines"], ["UVM_ERROR : 2"])

    def test_duplicate_actual_counters_rejected(self):
        with self.assertRaises(ValueError):
            parse_log("UVM_INFO f @ 1: top [VID/COUNT] allocations=0\n" * 2)

    def fixture(self):
        return dict(errors=[dict(tag="VID/NO_TRAFFIC", severity="ERROR")], counts={
            "CVXIF/COUNT": dict(requests=85, responses=85, aborted=0),
            "VID/COUNT": dict(allocations=0, completions=0, aborted=0, max_live=0)}), dict(
                events=dict(cvx_req=85, cvx_resp=85), trapped_responses=0,
                request_response_pairing=True, untrapped_vector_data_requests=0)

    def test_frontend_not_backend(self):
        parsed, trace = self.fixture()
        self.assertEqual(classify("vsetvli", parsed, trace)["classification"], "EXPECTED_FRONTEND_ONLY_ZERO_VID")
        self.assertFalse(vector_data(0xc0047057))
        self.assertTrue(vector_data(0x02000057))

    def test_unexpected_error_and_legal_operation_hold(self):
        parsed, trace = self.fixture()
        parsed["errors"].append(dict(tag="VID/DUP_ALLOC", severity="ERROR"))
        self.assertTrue(classify("vsetvli", parsed, trace)["issues"])
        parsed, trace = self.fixture()
        trace["untrapped_vector_data_requests"] = 1
        self.assertTrue(classify("vsetvli", parsed, trace)["issues"])

    def test_exact_bounded_expectations_and_unknown_hold(self):
        self.assertEqual((len(FRONT), len(SCALAR)), (9, 17))
        parsed, trace = self.fixture()
        self.assertTrue(classify("unknown", parsed, trace)["issues"])


if __name__ == "__main__":
    unittest.main()
