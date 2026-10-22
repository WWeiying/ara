import json
import sys
import tempfile
import unittest
from pathlib import Path

from linux.check_boot import check_stage_result
from linux.run_stage import run_stage


class LinuxStageTests(unittest.TestCase):
    def test_stage_requires_marker_and_records_payload_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Image"
            payload.write_bytes(b"image")
            result = run_stage(
                "qemu",
                root / "run",
                [sys.executable, "-c", "print('Linux marker')"],
                ["Linux marker"],
                {"kernel": payload},
                10,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["artifacts"]["kernel"]), 64)
            saved = json.loads((root / "run" / "stage_result.json").read_text())
            self.assertEqual(saved["status"], "PASS")
            self.assertEqual(len(saved["console_sha256"]), 64)
            self.assertTrue((root / "run" / "stage_result.sha256").is_file())
            checked = check_stage_result(
                root / "run" / "stage_result.json",
                expected_stage="qemu",
                required_markers=["Linux marker"],
            )
            self.assertEqual(checked["status"], "PASS")

    def test_stage_result_fails_if_artifact_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Image"
            payload.write_bytes(b"image")
            run_stage(
                "rtl",
                root / "run",
                [sys.executable, "-c", "print('boot')"],
                ["boot"],
                {"kernel": payload},
                10,
            )
            payload.write_bytes(b"changed")
            checked = check_stage_result(root / "run" / "stage_result.json")
            self.assertEqual(checked["status"], "FAIL")
            self.assertIn("stage artifact SHA-256 mismatch: kernel", checked["errors"])

    def test_stage_result_fails_if_console_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Image"
            payload.write_bytes(b"image")
            run_stage("rtl", root / "run",
                      [sys.executable, "-c", "print('boot')"],
                      ["boot"], {"kernel": payload}, 10)
            with (root / "run" / "console.log").open("a") as stream:
                stream.write("userspace PASS\n")
            checked = check_stage_result(root / "run" / "stage_result.json")
            self.assertEqual(checked["status"], "FAIL")
            self.assertIn("stage console SHA-256 mismatch", checked["errors"])

    def test_stage_fails_closed_when_marker_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_stage(
                "rtl",
                Path(directory) / "run",
                [sys.executable, "-c", "print('boot only')"],
                ["userspace PASS"],
                {},
                10,
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("missing marker: userspace PASS", result["errors"])

    def test_stage_result_without_payload_is_not_signoff_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_stage(
                "qemu",
                root / "run",
                [sys.executable, "-c", "print('boot')"],
                ["boot"],
                {},
                10,
            )
            self.assertEqual(result["status"], "PASS")
            checked = check_stage_result(root / "run" / "stage_result.json")
            self.assertEqual(checked["status"], "FAIL")
            self.assertIn("stage result must contain non-empty artifact hashes", checked["errors"])

    def test_malformed_stage_result_fails_without_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "stage_result.json"
            result_path.write_text("[]")
            checked = check_stage_result(result_path)
            self.assertEqual(checked["status"], "FAIL")
            self.assertIn("stage result must be a JSON object", checked["errors"])

    def test_stage_failure_marker_is_rejected_by_signoff_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Image"
            payload.write_bytes(b"image")
            run_stage(
                "qemu",
                root / "run",
                [sys.executable, "-c", "print('Linux marker; Kernel panic')"],
                ["Linux marker"],
                {"kernel": payload},
                10,
            )
            checked = check_stage_result(root / "run" / "stage_result.json")
            self.assertEqual(checked["status"], "FAIL")
            self.assertIn(
                "failure marker present in stage console: Kernel panic",
                checked["errors"],
            )

    def test_userspace_failure_and_real_watchdog_faults_are_rejected(self):
        for message, expected in (
            ("watchdog: driver registered", "PASS"),
            ("watchdog: BUG: soft lockup", "FAIL"),
            ("[LINUX_RVV] FAIL csr mismatch", "FAIL"),
            ("ARA_LINUX_USERSPACE FAIL", "FAIL"),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                payload = root / "Image"
                payload.write_bytes(b"unit-test-image")
                run_stage("qemu", root / "run",
                          [sys.executable, "-c", f"print('unit marker'); print({message!r})"],
                          ["unit marker"], {"kernel": payload}, 10)
                checked = check_stage_result(root / "run" / "stage_result.json")
                self.assertEqual(checked["status"], expected)


if __name__ == "__main__":
    unittest.main()
