import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "qbs/audit_profile_matrix.py"
SPEC = importlib.util.spec_from_file_location("qbs_profile_audit", MODULE)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def complete_log():
    lines = []
    for case_id, (profile, m, rows, pattern) in enumerate(sorted(AUDIT.expected_matrix())):
        lines.append(f"QBS RTL case {case_id} PASS profile={profile} M={m} "
                     f"rows={rows} pattern={pattern} first_cycles=7 repeat_cycles=6")
    lines.append(f"QBS profile engine PASS: {len(lines)} cases")
    return "\n".join(lines) + "\n"


class QbsProfileMatrixTests(unittest.TestCase):
    def test_full_matrix_is_focused_pass(self):
        report = AUDIT.audit(complete_log())
        self.assertEqual(report["status"], "PASS", report["issues"])
        self.assertEqual(report["passed_cases"], 448)
        self.assertEqual(report["profile_counts"]["Q8_0_WEIGHT"], 64)

    def test_missing_duplicate_and_error_cannot_pass(self):
        log = complete_log()
        first, second = log.splitlines()[:2]
        bad = AUDIT.audit(log.replace(first + "\n", second + "\n", 1) + "Error: failed\n")
        self.assertEqual(bad["status"], "INCOMPLETE")
        self.assertEqual(len(bad["missing"]), 1)
        self.assertEqual(len(bad["duplicates"]), 1)
        self.assertTrue(any("case IDs" in issue for issue in bad["issues"]))
        self.assertTrue(any("error" in issue for issue in bad["issues"]))
        self.assertEqual(AUDIT.audit(log.replace("QBS profile engine PASS", "NOT PASS"))
                         ["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
