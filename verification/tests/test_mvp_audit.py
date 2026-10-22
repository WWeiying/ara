import csv
import io
from pathlib import Path
import re
import unittest

from fpu import run_mvp_audit as audit

AUDIT_DIR = Path(__file__).resolve().parents[1] / "fpu"


class MVPAuditTests(unittest.TestCase):
    def setUp(self):
        self.cases = audit.load_cases(AUDIT_DIR / "cases.json")

    def test_fixed_oracles_independently_derived(self):
        self.assertEqual(audit.architectural_oracle(self.cases[0]), (0x3ff0000000000000, 0))
        self.assertEqual(audit.architectural_oracle(self.cases[3]), (0xfff0000000000000, 5))
        self.assertEqual(audit.architectural_oracle(self.cases[4]), (0xffffffff7f800000, 5))
        self.assertEqual(audit.architectural_oracle(self.cases[7]), (0x7fefffffffffffff, 5))

    def test_oracle_rejects_unboxed_fp32(self):
        case = {**self.cases[5], "a": "000000003f800000"}
        with self.assertRaises(ValueError):
            audit.architectural_oracle(case)

    def test_oracle_not_general_division_model(self):
        case = {**self.cases[0], "b": "4008000000000000"}
        with self.assertRaises(ValueError):
            audit.architectural_oracle(case)

    def test_expected_defect_is_never_control_match(self):
        for case in self.cases[:5]:
            row = {"result": case["predicted_result"], "flags": case["predicted_flags"]}
            self.assertEqual(audit.classify(case, row), "DEFECT_REPRODUCED")

    def test_fixed_hypothesis_is_not_called_reproduced(self):
        case = self.cases[0]
        self.assertEqual(audit.classify(case, {"result": case["expected_result"], "flags": "00"}),
                         "HYPOTHESIS_NOT_REPRODUCED")

    def test_unexpected_bits_are_not_expected_defect(self):
        self.assertEqual(audit.classify(self.cases[0], {"result": "0", "flags": "00"}),
                         "UNEXPECTED_DUT_MISMATCH")

    def test_malformed_csv_rejected(self):
        for text in ("a,b\n", "a,b\n1\n", "a,b\n1,2,3\n"):
            with self.assertRaises(ValueError):
                audit.parse_csv(text)

    def test_trace_format_matches_header(self):
        source = (AUDIT_DIR / "mvp_audit_tb.sv").read_text()
        for descriptor in ("trace_fd", "results_fd"):
            fmt = re.search(r'\$fwrite\(' + descriptor + r',\s*"(%[^"\n]+)"', source)[1]
            header = re.search(r'\$fwrite\(' + descriptor + r', "([a-z][^"\n]+)"', source)[1]
            self.assertEqual(len(re.findall(r"%[0-9]*[dbhts]", fmt)), len(header.split(",")))

    def synthetic_evidence(self):
        rows, trace = [], []
        for i, case in enumerate(self.cases):
            row = {"id": str(i), "name": case["name"], "format": str(case["format"]),
                   "rm": str(case["rm"]), **{key: case[key] for key in
                   ("a", "b", "expected_result", "expected_flags")},
                   "result": case["predicted_result"], "flags": case["predicted_flags"],
                   "latency": "20", "oracle_match": str(int(i >= 5))}
            for key in ("remainder", "quotient", "denominator", "norm_exp", "norm_mant",
                        "explicit_round", "rounded_exp", "rounded_mant", "sticky", "round_up",
                        "overflow", "remainder_nonzero"):
                row[key] = "0"
            rows.append(row)
            for phase, cycle, fire, done in (("pre", 10, "1", "0"),
                                             ("post_nba", 30, "0", "1"),
                                             ("pre", 31, "0", "1")):
                trace.append({**row, "case_id": str(i), "phase": phase, "cycle": str(cycle),
                              "fire": fire, "done": done})

        def render(records):
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
            return stream.getvalue()

        return render(rows), render(trace)

    def test_evidence_checker_and_missing_completion(self):
        results, trace = self.synthetic_evidence()
        completion = "AUDIT_COMPLETE cases=8 accepted=8 completed=8 pending=0\n"
        records, errors = audit.check_evidence(self.cases, completion, results, trace)
        self.assertFalse(errors)
        self.assertEqual(records[0]["classification"], "DEFECT_REPRODUCED")
        self.assertTrue(audit.check_evidence(self.cases, "", results, trace)[1])
        self.assertTrue(audit.check_evidence(self.cases, completion * 2, results, trace)[1])
        self.assertTrue(audit.check_evidence(self.cases, completion + "HARNESS_ERROR", results, trace)[1])

    def test_duplicate_done_rejected(self):
        results, trace = self.synthetic_evidence()
        trace += trace.splitlines()[3] + "\n"
        self.assertTrue(audit.check_evidence(self.cases,
            "AUDIT_COMPLETE cases=8 accepted=8 completed=8 pending=0\n", results, trace)[1])


if __name__ == "__main__":
    unittest.main()
