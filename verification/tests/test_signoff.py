import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_signoff import REPO_ROOT, main, run_command
from linux.check_boot import DEFAULT_MARKERS, USERSPACE_MARKERS
from fpga.check_run import SIGNOFF_CONSOLE_MARKERS, check_manifest
from linux.run_stage import run_stage


class SignoffRunnerTests(unittest.TestCase):
    def test_subprocess_gates_export_verification_pythonpath(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gate.log"
            with patch("run_signoff.subprocess.run") as runner:
                runner.return_value.returncode = 0
                run_command("probe", ["python3", "-c", "pass"], log, False)
            env = runner.call_args.kwargs["env"]
            self.assertIn(str(REPO_ROOT / "verification"), env["PYTHONPATH"].split(":"))

    def test_default_preflight_dry_run_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preflight"
            self.assertEqual(main(["--output", str(output), "--dry-run"]), 0)
            payload = json.loads((output / "signoff.json").read_text())
            self.assertEqual(payload["status"], "DRY_RUN")
            self.assertEqual([gate["status"] for gate in payload["gates"]], ["NOT_RUN"] * 4)
            unit_gate = next(gate for gate in payload["gates"] if gate["name"] == "unit_tests")
            self.assertEqual(unit_gate["command"][1:],
                             ["-m", "pytest", "-q", "verification/tests"])

    def test_legacy_linux_log_is_not_signoff_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "uart.log"
            log.write_text("\n".join([*DEFAULT_MARKERS, "userspace PASS"]) + "\n")
            output = root / "linux"
            self.assertNotEqual(main([
                "--stage", "linux", "--output", str(output),
                "--linux-log", str(log), "--linux-userspace-marker", "userspace PASS",
            ]), 0)
            payload = json.loads((output / "signoff.json").read_text())
            self.assertEqual(payload["status"], "INCOMPLETE")
            self.assertEqual(payload["gates"][0]["status"], "NOT_CONFIGURED")

    def test_linux_soc_gate_requires_frozen_run_and_rejects_mixed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "not-a-run"
            self.assertNotEqual(main([
                "--stage", "linux", "--linux-soc-run", str(missing),
                "--output", str(root / "missing-gate")
            ]), 0)
            result = json.loads((root / "missing-gate" / "signoff.json").read_text())
            self.assertEqual(result["gates"][0]["status"], "NOT_CONFIGURED")

            frozen = root / "frozen"
            frozen.mkdir()
            self.assertNotEqual(main([
                "--stage", "linux", "--linux-soc-run", str(frozen),
                "--linux-stage", "rtl", "--output", str(root / "mixed-gate")
            ]), 0)
            result = json.loads((root / "mixed-gate" / "signoff.json").read_text())
            self.assertEqual(result["gates"][0]["status"], "NOT_CONFIGURED")

    def test_linux_soc_gate_reaudits_frozen_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen = root / "frozen"
            frozen.mkdir()
            args = ["--stage", "linux", "--linux-soc-run", str(frozen)]
            with patch("run_signoff.audit_soc_linux") as audit:
                audit.return_value = {"status": "FAIL", "errors": ["missing userspace marker"]}
                self.assertNotEqual(main([*args, "--output", str(root / "failed")]), 0)
                audit.return_value = {"status": "PASS", "errors": []}
                self.assertEqual(main([*args, "--output", str(root / "passed")]), 0)
            self.assertEqual(audit.call_count, 2)
            self.assertEqual(json.loads((root / "passed" / "linux.json").read_text())["status"],
                             "PASS")

    def test_uvm_gate_requires_real_dut_audits(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "uvm"
            self.assertNotEqual(main(["--stage", "uvm", "--output", str(output)]), 0)
            payload = json.loads((output / "signoff.json").read_text())
            self.assertEqual(payload["status"], "INCOMPLETE")
            self.assertEqual(payload["gates"][0]["status"], "NOT_CONFIGURED")

    def test_qbs_pair_gate_requires_and_reaudits_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertNotEqual(main([
                "--stage", "qbs-pairs", "--output", str(root / "missing")
            ]), 0)
            missing = json.loads((root / "missing" / "signoff.json").read_text())
            self.assertEqual(missing["gates"][0]["status"], "NOT_CONFIGURED")

            manifest = root / "manifest.json"
            manifest.write_text('{"schema_version": 1, "qbs_pairs": []}')
            self.assertNotEqual(main([
                "--stage", "qbs-pairs", "--qbs-pair-manifest", str(manifest),
                "--output", str(root / "invalid")
            ]), 0)
            invalid = json.loads((root / "invalid" / "signoff.json").read_text())
            self.assertEqual(invalid["gates"][0]["status"], "FAIL")
            self.assertEqual(json.loads((root / "invalid" / "qbs_pairs.json").read_text())["status"],
                             "INCOMPLETE")

    def test_coverage_integrity_gate_requires_frozen_merge_and_reaudits_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertNotEqual(main([
                "--stage", "coverage-integrity", "--output", str(root / "missing")
            ]), 0)
            missing = json.loads((root / "missing" / "signoff.json").read_text())
            self.assertEqual(missing["gates"][0]["status"], "NOT_CONFIGURED")

            merge = root / "merge" / "audit.json"
            merge.parent.mkdir()
            merge.write_text('{"status": "PASS", "cases": []}')
            self.assertNotEqual(main([
                "--stage", "coverage-integrity", "--coverage-merge-audit", str(merge),
                "--output", str(root / "invalid")
            ]), 0)
            invalid = json.loads((root / "invalid" / "signoff.json").read_text())
            self.assertEqual(invalid["gates"][0]["status"], "FAIL")
            self.assertEqual(json.loads((root / "invalid" / "coverage_integrity.json").read_text())["status"],
                             "FAIL")
            self.assertTrue(invalid["policy"]["coverage_integrity_does_not_establish_coverage_closure"])

            with patch("run_signoff.run_command") as runner:
                runner.return_value = {"name": "coverage-integrity", "status": "PASS"}
                self.assertEqual(main([
                    "--stage", "coverage-integrity", "--coverage-merge-audit", str(merge),
                    "--coverage-minimum-cases", "4", "--output", str(root / "wired")
                ]), 0)
            command = runner.call_args.args[1]
            self.assertEqual(command[1:4], [REPO_ROOT / "verification" / "coverage" / "audit_merged.py",
                                             "--audit", merge.resolve()])
            self.assertEqual(command[4:6], ["--minimum-cases", 4])

    def test_uvm_gate_reaudits_cases_and_rejects_missing_bins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit = root / "case" / "uvm_result.json"
            args = ["--stage", "uvm", "--uvm-audit", str(audit)]
            with patch("run_signoff.collect_uvm_coverage") as collector:
                collector.return_value = {"status": "INCOMPLETE", "missing_bins": ["axi_reset_aborts_read"]}
                self.assertNotEqual(main([*args, "--output", str(root / "incomplete")]), 0)
                collector.assert_called_once_with([audit])
                collector.return_value = {"status": "PASS", "missing_bins": [], "run_count": 1}
                self.assertEqual(main([*args, "--output", str(root / "closed")]), 0)
            self.assertEqual(json.loads((root / "incomplete" / "signoff.json").read_text())["status"],
                             "INCOMPLETE")
            self.assertEqual(json.loads((root / "closed" / "uvm.json").read_text())["status"],
                             "PASS")

    def test_fpga_gate_requires_manifest_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitstream = root / "design.bit"
            software = root / "smoke.elf"
            console = root / "console.log"
            bitstream.write_bytes(b"bitstream")
            software.write_bytes(b"software")
            console.write_text("\n".join([*SIGNOFF_CONSOLE_MARKERS, "board smoke PASS"]) + "\n")
            evidence_dir = root / "evidence"
            evidence_dir.mkdir()
            evidence_files = {}
            for name in (
                "reset_uart_ddr", "baremetal_rvv_signature", "linux_boot",
                "rvv_fallback_userspace", "qbs_akv_userspace",
                "context_switch_and_fault_return", "long_model_smoke",
            ):
                log = evidence_dir / f"{name}.log"
                result = evidence_dir / f"{name}.json"
                log.write_text(f"{name} PASS\n")
                result.write_text(json.dumps({"status": "PASS", "name": name}) + "\n")
                evidence_files[name] = {
                    "log": str(log),
                    "result": str(result),
                    "input_hashes": {"software": "a" * 64},
                }
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "board": "VCU118",
                "bitstream_tool": "Vivado",
                "vivado_version": "2020.1",
                "rtl_commit": "deadbeef",
                "clock_mhz": 50,
                "flow_status": "COMPLETE",
                "bitstream_generated": True,
                "artifacts": {
                    "bitstream": {"path": str(bitstream), "sha256": hashlib.sha256(bitstream.read_bytes()).hexdigest()},
                    "software": {"path": str(software), "sha256": hashlib.sha256(software.read_bytes()).hexdigest()},
                },
                "ddr_calibration": True,
                "reset_uart_smoke": True,
                "console_log": str(console),
                "console_markers": [*SIGNOFF_CONSOLE_MARKERS, "board smoke PASS"],
                "tests": [
                    {
                        "name": name, "status": "PASS",
                        "command": ["board-test", name],
                        "evidence": evidence_files[name],
                    }
                    for name in (
                        "reset_uart_ddr", "baremetal_rvv_signature", "linux_boot",
                        "rvv_fallback_userspace", "qbs_akv_userspace",
                        "context_switch_and_fault_return", "long_model_smoke",
                    )
                ],
            }))
            output = root / "fpga"
            self.assertEqual(main([
                "--stage", "fpga", "--output", str(output),
                "--fpga-manifest", str(manifest),
            ]), 0)
            payload = json.loads((output / "signoff.json").read_text())
            self.assertEqual(payload["status"], "PASS")

    def test_missing_differential_inputs_are_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "missing"
            self.assertNotEqual(main([
                "--stage", "differential", "--output", str(output),
            ]), 0)
            payload = json.loads((output / "signoff.json").read_text())
            self.assertEqual(payload["status"], "INCOMPLETE")
            self.assertEqual(payload["gates"][0]["status"], "NOT_CONFIGURED")

    def test_incomplete_fpga_manifest_fails_strict_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitstream = root / "design.bit"
            software = root / "smoke.elf"
            console = root / "console.log"
            bitstream.write_bytes(b"bitstream")
            software.write_bytes(b"software")
            console.write_text("\n".join(SIGNOFF_CONSOLE_MARKERS) + "\n")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1, "board": "VCU118",
                "bitstream_tool": "Vivado", "vivado_version": "2020.1",
                "rtl_commit": "deadbeef", "clock_mhz": 50,
                "flow_status": "COMPLETE", "bitstream_generated": True,
                "artifacts": {
                    "bitstream": {"path": str(bitstream)},
                    "software": {"path": str(software)},
                },
                "ddr_calibration": True, "reset_uart_smoke": True,
                "console_log": str(console),
                "console_markers": list(SIGNOFF_CONSOLE_MARKERS),
                "tests": [{"name": name, "status": "PASS"} for name in (
                    "reset_uart_ddr", "baremetal_rvv_signature", "linux_boot",
                    "rvv_fallback_userspace", "qbs_akv_userspace",
                    "context_switch_and_fault_return", "long_model_smoke",
                )],
            }))
            checked = check_manifest(manifest, require_signoff=True)
            self.assertEqual(checked["status"], "FAIL")
            self.assertTrue(any("SHA-256" in error for error in checked["errors"]))
            self.assertTrue(any("evidence" in error for error in checked["errors"]))

    def test_linux_signoff_consumes_stage_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Image"
            payload.write_bytes(b"image")
            stage = root / "stage"
            markers = [*DEFAULT_MARKERS, "Linux marker"]
            run_stage(
                "qemu", stage,
                ["python3", "-c", f"print({markers!r})"],
                markers, {"Image": payload}, 10,
            )
            output = root / "signoff"
            self.assertEqual(main([
                "--stage", "linux", "--output", str(output),
                "--linux-stage-result", str(stage / "stage_result.json"),
                "--linux-stage", "qemu", "--linux-userspace-marker", "Linux marker",
            ]), 0)
            payload_json = json.loads((output / "signoff.json").read_text())
            self.assertEqual(payload_json["status"], "PASS")

    def test_linux_userspace_profile_does_not_claim_board_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Image"
            payload.write_bytes(b"unit-test-image")
            stage = root / "stage"
            markers = [*USERSPACE_MARKERS, "RVV fallback userspace PASS"]
            run_stage("qemu", stage, ["python3", "-c", f"print({markers!r})"],
                      markers, {"Image": payload}, 10)
            common = ["--stage", "linux", "--linux-stage-result", str(stage / "stage_result.json"),
                      "--linux-boot-profile", "userspace", "--linux-userspace-marker",
                      "RVV fallback userspace PASS"]
            self.assertEqual(main([*common, "--linux-stage", "qemu",
                                   "--output", str(root / "qemu")]), 0)
            self.assertNotEqual(main([*common, "--linux-stage", "board",
                                      "--output", str(root / "board")]), 0)


if __name__ == "__main__":
    unittest.main()
