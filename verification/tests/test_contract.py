import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.contract import check_contract_log


VERIFICATION = Path(__file__).resolve().parents[1]
SUMMARY = (
    "[ARA_CONTRACT] requests=4 responses=4 exceptions=0 mmu_request_cycles=0 "
    "protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0"
)
CORE_SUCCESS = "Core Test *** SUCCESS *** (tohost = 0)"


class ContractTests(unittest.TestCase):
    def check_log(self, text, require_core_success=True):
        # Keep all fixtures in memory; the checker itself only reads logs.
        with patch("ara_verify.contract.Path.read_text", return_value=text):
            return check_contract_log(Path("run.log"), require_core_success)

    def assert_issue(self, text, expected, require_core_success=True):
        issues = self.check_log(text, require_core_success)
        self.assertTrue(any(expected in issue for issue in issues), issues)

    def test_positive_actual_dut_log(self):
        text = f"VCS simulator\nInfo: {CORE_SUCCESS}\n{SUMMARY}\nCPU time: 0.1 seconds\n"
        self.assertEqual([], self.check_log(text))

    def test_positive_monitor_only_log(self):
        self.assertEqual([], self.check_log(SUMMARY, require_core_success=False))

    def test_string_path_is_supported(self):
        with patch("ara_verify.contract.Path.read_text", return_value=SUMMARY) as read:
            self.assertEqual([], check_contract_log("run.log", require_core_success=False))
        read.assert_called_once_with(encoding="utf-8")

    def test_informational_counters_can_be_nonzero(self):
        summary = SUMMARY.replace("exceptions=0", "exceptions=2").replace(
            "mmu_request_cycles=0", "mmu_request_cycles=100"
        )
        self.assertEqual([], self.check_log(f"{CORE_SUCCESS}\n{summary}"))

    def test_crlf_and_surrounding_whitespace(self):
        text = f"{CORE_SUCCESS}\r\n\t{SUMMARY}  \r\nUVM_ERROR :    0\r\n"
        self.assertEqual([], self.check_log(text))

    def test_missing_summary(self):
        for text in ("", CORE_SUCCESS, "[ARA_CONTRACT_ERROR] no traffic"):
            with self.subTest(text=text):
                self.assert_issue(text, "exactly one [ARA_CONTRACT] summary, found 0")

    def test_all_summary_fields_are_required(self):
        for field in SUMMARY.split()[1:]:
            with self.subTest(field=field):
                summary = SUMMARY.replace(f" {field}", "")
                self.assert_issue(f"{CORE_SUCCESS}\n{summary}", "malformed")

    def test_all_summary_values_must_be_unsigned_decimal(self):
        for field in SUMMARY.split()[1:]:
            name = field.split("=", 1)[0]
            for value in ("", "-1", "+1", "x", "z", "0x0", "0.0", "1_0", "0junk", "\u0660"):
                with self.subTest(field=name, value=value):
                    summary = SUMMARY.replace(field, f"{name}={value}")
                    self.assert_issue(f"{CORE_SUCCESS}\n{summary}", "malformed")

    def test_malformed_summary_structure(self):
        summaries = (
            SUMMARY.replace("mmu_request_cycles", "mmu_requests"),
            SUMMARY.replace("requests=4 responses=4", "responses=4 requests=4"),
            SUMMARY + " protocol_errors=0",
            SUMMARY + " extra=0",
            SUMMARY + " trailing text",
            "echo " + SUMMARY,
            SUMMARY.replace(" outstanding", "\noutstanding"),
        )
        for summary in summaries:
            with self.subTest(summary=summary):
                self.assert_issue(f"{CORE_SUCCESS}\n{summary}", "malformed")

    def test_multiple_summaries_even_when_identical(self):
        for separator in ("\n", " "):
            with self.subTest(separator=separator):
                self.assert_issue(
                    f"{CORE_SUCCESS}\n{SUMMARY}{separator}{SUMMARY}",
                    "exactly one [ARA_CONTRACT] summary, found 2",
                )

    def test_valid_summary_does_not_mask_malformed_summary(self):
        malformed = "[ARA_CONTRACT] requests=4 responses=4 protocol_errors=0"
        for records in (f"{malformed}\n{SUMMARY}", f"{SUMMARY}\n{malformed}"):
            with self.subTest(records=records):
                text = f"{CORE_SUCCESS}\n{records}"
                self.assert_issue(text, "malformed")
                self.assert_issue(text, "exactly one [ARA_CONTRACT] summary, found 2")

    def test_zero_traffic_fails(self):
        for name in ("requests", "responses"):
            with self.subTest(name=name):
                summary = SUMMARY.replace(f"{name}=4", f"{name}=0")
                self.assert_issue(f"{CORE_SUCCESS}\n{summary}", f"{name} must be nonzero")
        summary = SUMMARY.replace("requests=4 responses=4", "requests=0 responses=0")
        self.assert_issue(f"{CORE_SUCCESS}\n{summary}", "must be nonzero")

    def test_unbalanced_traffic_in_both_directions(self):
        for responses in (3, 5):
            with self.subTest(responses=responses):
                summary = SUMMARY.replace("responses=4", f"responses={responses}")
                self.assert_issue(f"{CORE_SUCCESS}\n{summary}", "must be equal")

    def test_errors_outstanding_and_stalls_fail_despite_balanced_traffic(self):
        for name in ("protocol_errors", "outstanding", "req_stalled", "resp_stalled"):
            for value in (1, 10):
                with self.subTest(name=name, value=value):
                    summary = SUMMARY.replace(f"{name}=0", f"{name}={value}")
                    self.assert_issue(f"{CORE_SUCCESS}\n{summary}", f"{name}={value}")

    def test_payload_errors_fail_despite_zero_error_counter(self):
        diagnostics = (
            "[ARA_CONTRACT_ERROR] request payload changed while stalled",
            "[ARA_CONTRACT_ERROR] response payload changed while stalled",
            "Error: monitor.sv:42: assertion failed",
            "Fatal: simulation terminated",
            "Error-[ASRTST] Assertion failed",
            "Fatal-[ASRTST] Assertion failed",
            "monitor.sv:42: Error: payload changed",
            "UVM_ERROR @ 10: reporter [CONTRACT] request payload changed",
            "UVM_FATAL monitor.sv(42) @ 10: reporter [CONTRACT] failed",
        )
        for diagnostic in diagnostics:
            for after_summary in (False, True):
                with self.subTest(diagnostic=diagnostic, after_summary=after_summary):
                    records = (
                        f"{SUMMARY}\n{diagnostic}" if after_summary
                        else f"{diagnostic}\n{SUMMARY}"
                    )
                    text = f"{CORE_SUCCESS}\n{records}\nUVM_ERROR : 0\nUVM_FATAL : 0"
                    self.assert_issue(text, diagnostic)

    def test_uvm_zero_counts_are_not_errors(self):
        for counts in (
            "UVM_ERROR :    0\nUVM_FATAL :    0",
            "  UVM_ERROR:0  \n\tUVM_FATAL\t:\t00\t",
        ):
            with self.subTest(counts=counts):
                self.assertEqual([], self.check_log(f"{CORE_SUCCESS}\n{SUMMARY}\n{counts}"))

    def test_uvm_nonzero_or_malformed_counts_fail(self):
        for severity in ("UVM_ERROR", "UVM_FATAL"):
            for count in ("1", "10", "01", "-1", "x", "", "0.1", "0 payload changed"):
                with self.subTest(severity=severity, count=count):
                    self.assert_issue(
                        f"{CORE_SUCCESS}\n{SUMMARY}\n{severity} : {count}\n{severity} : 0",
                        "UVM diagnostic",
                    )

    def test_uvm_zero_count_cannot_hide_diagnostic_on_same_line(self):
        self.assert_issue(
            f"{CORE_SUCCESS}\n{SUMMARY}\nUVM_ERROR : 0 UVM_FATAL @ 10: failed",
            "UVM diagnostic",
        )

    def test_core_success_is_required_by_default(self):
        self.assert_issue(SUMMARY, "missing Core Test *** SUCCESS")

    def test_partial_core_success_is_not_accepted(self):
        for marker in ("Core Test *** SUCCES", "Core Test *** SUCCESSFUL"):
            with self.subTest(marker=marker):
                self.assert_issue(f"{marker}\n{SUMMARY}", "missing Core Test *** SUCCESS")

    def test_core_failure_is_not_hidden_by_success(self):
        text = f"{CORE_SUCCESS}\nCore Test *** FAILED ***\n{SUMMARY}"
        for require_core_success in (False, True):
            with self.subTest(require_core_success=require_core_success):
                self.assert_issue(text, "Core Test failure", require_core_success)

    def test_monitor_only_mode_still_requires_valid_contract(self):
        for text in ("", SUMMARY + "\n" + SUMMARY, SUMMARY + "\nError: failed"):
            with self.subTest(text=text):
                self.assertTrue(self.check_log(text, require_core_success=False))

    def test_unreadable_logs_return_issues(self):
        for error in (
            FileNotFoundError("missing log"),
            PermissionError("unreadable log"),
            IsADirectoryError("not a log"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid encoding"),
        ):
            with self.subTest(error=error):
                with patch("ara_verify.contract.Path.read_text", side_effect=error):
                    issues = check_contract_log("run.log")
                self.assertEqual(1, len(issues))
                self.assertIn("cannot read contract log", issues[0])


class ContractCliTests(unittest.TestCase):
    def run_cli(self, text, *args):
        return subprocess.run(
            [sys.executable, "-B", "-m", "ara_verify.contract", "/dev/stdin", *args],
            input=text,
            text=True,
            capture_output=True,
            cwd=VERIFICATION,
            timeout=5,
            check=False,
        )

    def test_default_cli_accepts_actual_dut_success(self):
        result = self.run_cli(f"{CORE_SUCCESS}\n{SUMMARY}")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertEqual("", result.stderr)

    def test_default_cli_rejects_missing_core_success(self):
        result = self.run_cli(SUMMARY)
        self.assertEqual(1, result.returncode)
        self.assertIn("missing Core Test *** SUCCESS", result.stderr)
        self.assertNotIn("PASS", result.stdout)

    def test_cli_can_disable_core_success_requirement(self):
        result = self.run_cli(SUMMARY, "--no-core-success")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_cli_issues_return_one_in_both_modes(self):
        for args in ((), ("--no-core-success",)):
            with self.subTest(args=args):
                result = self.run_cli(f"{CORE_SUCCESS}\n{SUMMARY}\nError: payload changed", *args)
                self.assertEqual(1, result.returncode)
                self.assertIn("Error: payload changed", result.stderr)
                self.assertNotIn("PASS", result.stdout)

    def test_cli_missing_summary_returns_one(self):
        result = self.run_cli(CORE_SUCCESS)
        self.assertEqual(1, result.returncode)
        self.assertIn("exactly one [ARA_CONTRACT] summary, found 0", result.stderr)


if __name__ == "__main__":
    unittest.main()
