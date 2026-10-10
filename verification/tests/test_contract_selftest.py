import io
import signal
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import run_contract_selftest as runner


POSITIVE_CASES = ("legal", "reset")
NEGATIVE_CASES = (
    "duplicate", "orphan", "request_drop", "response_drop", "request_payload",
    "request_frm", "response_payload", "exception_payload", "unknown",
    "error_then_reset", "incomplete",
)
CASES = POSITIVE_CASES + NEGATIVE_CASES
EXPECTED_ERRORS = {case: int(case not in ("legal", "reset", "incomplete")) for case in CASES}
OUTPUT = Path("/mock/contract-selftest")


def completion(case):
    return f"[SELFTEST_PASS] case={case} expected_errors={EXPECTED_ERRORS[case]}\n"


def complete_log(case):
    errors = EXPECTED_ERRORS[case]
    incomplete = int(case == "incomplete")
    diagnostic = "[ARA_CONTRACT_ERROR] injected violation\n" if errors else ""
    return (
        diagnostic + completion(case)
        + f"[ARA_CONTRACT] requests=1 responses={1 - incomplete} exceptions=0 "
        + f"mmu_request_cycles=0 protocol_errors={errors} outstanding={incomplete} "
        + "req_stalled=0 resp_stalled=0\n"
    )


class ContractSelftestTests(unittest.TestCase):
    def run_selftest(self, overrides=None, stale_logs=False):
        overrides = overrides or {}
        # Model deletion and fresh simulator output without touching the filesystem.
        files = {
            OUTPUT / f"{case}.log": complete_log(case) for case in CASES
        } if stale_logs else {}

        def unlink(path, missing_ok=False):
            if path not in files and not missing_ok:
                raise FileNotFoundError(path)
            files.pop(path, None)

        def read_text(path, *args, **kwargs):
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        def launch(command, **kwargs):
            case = next(arg.split("=", 1)[1] for arg in command if arg.startswith("+CASE="))
            log = Path(command[command.index("-l") + 1])
            returncode, fresh_log, stdout = overrides.get(
                case, (int(case in NEGATIVE_CASES), complete_log(case), "")
            )
            if fresh_log is not None:
                files[log] = fresh_log
            return subprocess.CompletedProcess(command, returncode, stdout=stdout)

        output = io.StringIO()
        with patch.object(sys, "argv", ["run_contract_selftest.py", "/mock/simv",
                                       "--output", str(OUTPUT)]), \
             patch.object(runner.Path, "mkdir"), \
             patch.object(runner.Path, "unlink", unlink), \
             patch.object(runner.Path, "is_file", lambda path: path in files), \
             patch.object(runner.Path, "read_text", read_text), \
             patch.object(runner.subprocess, "run", side_effect=launch) as run, \
             redirect_stdout(output):
            returncode = runner.main()
        self.assertEqual(len(CASES), run.call_count)
        return int(returncode), output.getvalue()

    def assert_case_rejected(self, case, result, stale_logs=False):
        returncode, output = self.run_selftest({case: result}, stale_logs=stale_logs)
        self.assertEqual(1, returncode, output)
        self.assertIn(f"FAIL {case}:", output)
        self.assertIn(f"contract selftest: {len(CASES) - 1}/{len(CASES)} passed", output)

    def test_fresh_completed_negative_controls_are_accepted(self):
        for negative_returncode in (0, 1):
            with self.subTest(returncode=negative_returncode):
                overrides = {
                    case: (negative_returncode, complete_log(case), "")
                    for case in NEGATIVE_CASES
                }
                returncode, output = self.run_selftest(overrides)
                self.assertEqual(0, returncode, output)
                for case in NEGATIVE_CASES:
                    self.assertIn(f"PASS {case}: rejected by log gate", output)
                self.assertIn(f"contract selftest: {len(CASES)}/{len(CASES)} passed", output)

    def test_failed_negative_launch_cannot_reuse_stale_pass_log(self):
        for case in NEGATIVE_CASES:
            with self.subTest(case=case):
                self.assert_case_rejected(
                    case, (1, None, "Error-[LICENSE] simulator never started\n"),
                    stale_logs=True,
                )

    def test_positive_completion_without_summary_is_rejected(self):
        for case in POSITIVE_CASES:
            with self.subTest(case=case):
                self.assert_case_rejected(case, (0, completion(case), ""))

    def test_negative_completion_without_summary_is_rejected(self):
        for case in NEGATIVE_CASES:
            with self.subTest(case=case):
                self.assert_case_rejected(case, (1, completion(case), ""))

    def test_malformed_summary_is_rejected(self):
        for case in ("legal", "request_payload", "incomplete"):
            log = complete_log(case)
            malformed_logs = (
                log.replace(" resp_stalled=0", ""),
                log.replace(f"protocol_errors={EXPECTED_ERRORS[case]}", "protocol_errors=x"),
                log.replace("requests=1", "requests=-1"),
                log.replace("resp_stalled=0", "resp_stalled=0 extra=0"),
            )
            for malformed in malformed_logs:
                with self.subTest(case=case, log=malformed):
                    self.assert_case_rejected(case, (int(case in NEGATIVE_CASES), malformed, ""))

    def test_multiple_summaries_are_rejected(self):
        for case in ("legal", "request_payload", "incomplete"):
            log = complete_log(case)
            summary = log.splitlines()[-1]
            for separator in ("\n", " "):
                with self.subTest(case=case, separator=separator):
                    duplicate = log.replace(summary, summary + separator + summary)
                    self.assert_case_rejected(case, (int(case in NEGATIVE_CASES), duplicate, ""))

    def test_valid_summary_cannot_hide_malformed_record(self):
        for case in ("request_payload", "incomplete"):
            log = complete_log(case)
            malformed = "[ARA_CONTRACT] requests=1\n"
            for records in (malformed + log, log + malformed):
                with self.subTest(case=case, log=records):
                    self.assert_case_rejected(case, (1, records, ""))

    def test_protocol_error_count_must_match_each_case(self):
        for case, expected in EXPECTED_ERRORS.items():
            for wrong in (0, 1, 2):
                if wrong == expected:
                    continue
                with self.subTest(case=case, errors=wrong):
                    log = complete_log(case).replace(
                        f"protocol_errors={expected}", f"protocol_errors={wrong}"
                    )
                    self.assert_case_rejected(case, (int(case in NEGATIVE_CASES), log, ""))

    def test_stdout_evidence_without_fresh_log_is_rejected(self):
        for case in ("legal", "request_payload", "incomplete"):
            with self.subTest(case=case):
                self.assert_case_rejected(
                    case, (int(case in NEGATIVE_CASES), None, complete_log(case)),
                    stale_logs=True,
                )

    def test_positive_nonzero_returncode_is_rejected(self):
        for case in POSITIVE_CASES:
            with self.subTest(case=case):
                self.assert_case_rejected(case, (1, complete_log(case), ""))

    def test_negative_signal_or_abnormal_exit_is_rejected(self):
        case = "request_payload"
        for returncode in (-signal.SIGKILL, 2, 128 + signal.SIGKILL):
            with self.subTest(returncode=returncode):
                self.assert_case_rejected(case, (returncode, complete_log(case), ""))

    def test_negative_rejection_without_fresh_completion_is_rejected(self):
        case = "request_payload"
        log = complete_log(case).replace(completion(case), "")
        self.assert_case_rejected(case, (1, log, ""), stale_logs=True)

    def test_negative_control_accepted_by_log_gate_is_rejected(self):
        case = "incomplete"
        log = complete_log("legal").replace(completion("legal"), completion(case))
        self.assert_case_rejected(case, (0, log, ""))


if __name__ == "__main__":
    unittest.main()
