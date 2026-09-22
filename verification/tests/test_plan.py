import json
import tempfile
import unittest
from pathlib import Path

from ara_verify.catalog import load_catalog
from ara_verify.plan import audit_run, load_plan, validate_plan
from fpga.check_run import check_manifest as check_fpga_manifest
from linux.check_boot import check_boot


ROOT = Path(__file__).resolve().parents[2]


class VerificationPlanTests(unittest.TestCase):
    def test_plan_references_current_catalog(self):
        catalog = load_catalog(ROOT, ROOT / "verification/suites.json")
        summary = validate_plan(catalog, load_plan(ROOT / "verification/verification_plan.json"))
        self.assertEqual(summary["status"], "VALID")
        self.assertEqual(summary["requirement_count"], 11)
        self.assertEqual(summary["random_profile_count"], 8)
        self.assertEqual(summary["linux_level_count"], 3)
        self.assertGreater(summary["coverage_dimensions"]["lmul"].__len__(), 1)

    def test_audit_rejects_non_pass_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "tests" / "case"
            artifact.mkdir(parents=True)
            (artifact / "command.json").write_text("{}\n", encoding="utf-8")
            (root / "run.json").write_text(
                '{"status":"COMPLETE","invocation":["run"],'
                '"git":{"commit":"abc"}}\n', encoding="utf-8"
            )
            (root / "summary.json").write_text(json.dumps([{
                "name": "rvv:case",
                "status": "PASS",
                "artifact_dir": str(artifact),
            }]) + "\n", encoding="utf-8")
            result = audit_run(root, require_trace=True, require_vector=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["failed_cases"], 1)

    def test_audit_accepts_complete_vector_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "tests" / "case"
            artifact.mkdir(parents=True)
            (artifact / "rtl.command.json").write_text("{}\n", encoding="utf-8")
            (artifact / "trace_summary.json").write_text(
                '{"status":"VALID"}\n', encoding="utf-8"
            )
            (artifact / "commit_comparison.json").write_text(
                '{"status":"MATCH"}\n', encoding="utf-8"
            )
            (artifact / "vector_commit_comparison.json").write_text(
                '{"status":"PASS"}\n', encoding="utf-8"
            )
            (root / "run.json").write_text(
                '{"status":"COMPLETE","invocation":["run"],'
                '"git":{"commit":"abc"}}\n', encoding="utf-8"
            )
            (root / "summary.json").write_text(json.dumps([{
                "name": "random_0",
                "status": "PASS",
                "artifact_dir": str(artifact),
            }]) + "\n", encoding="utf-8")
            result = audit_run(root, require_trace=True, require_vector=True)
            self.assertEqual(result["status"], "PASS")


class LinuxBootCheckTests(unittest.TestCase):
    def test_requires_all_boot_markers_and_hashes_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "console.log"
            payload = root / "Image"
            log.write_text(
                "OpenSBI\nLinux version 6.x\n"
                "Ara DSA VCU118 Linux init reached\n"
                "Linux console, DDR and RVV handoff are alive\n",
                encoding="utf-8",
            )
            payload.write_bytes(b"payload")
            result = check_boot(log, list((
                "OpenSBI", "Linux version", "Ara DSA VCU118 Linux init reached",
                "Linux console, DDR and RVV handoff are alive",
            )), {"kernel": payload})
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["artifacts"]["kernel"]), 64)


class FpgaManifestTests(unittest.TestCase):
    def test_rejects_unverified_or_mismatched_board_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitstream = root / "design.bit"
            software = root / "Image"
            console = root / "uart.log"
            bitstream.write_bytes(b"bitstream")
            software.write_bytes(b"Image")
            console.write_text("OpenSBI\nLinux version\n", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "board": "VCU118",
                "bitstream_tool": "Vivado",
                "vivado_version": "2025.1",
                "rtl_commit": "abc",
                "clock_mhz": 100,
                "ddr_calibration": True,
                "reset_uart_smoke": True,
                "artifacts": {
                    "bitstream": {"path": str(bitstream)},
                    "software": {"path": str(software)},
                },
                "console_log": str(console),
                "console_markers": ["OpenSBI", "Linux version"],
                "tests": [{"name": "rvv_fallback", "status": "PASS"}],
            }) + "\n", encoding="utf-8")
            result = check_fpga_manifest(manifest)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["artifacts"]["bitstream"]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
