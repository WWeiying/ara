"""Negative runner gates and mocked lifecycle; never starts an EDA process."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_gap95_simulation as runner


class Gap95RunnerTests(unittest.TestCase):
    def preflight(self):
        return runner.read_bound(runner.PRE / "preflight-manifest.json", runner.PRE_SEAL)

    def test_all_case_commands(self):
        for case in runner.CASES:
            row = runner.validate_preflight(self.preflight(), case)
            output = runner.OUT / ("unlaunched-gap95-test-" + case)
            command = runner.make_command(row, output)
            self.assertEqual(command[0], str(runner.IMAGE))
            self.assertIn("+PRELOAD=" + str(runner.PRE / row["case"] / "input.elf"), command)
            self.assertIn("+TESTCASE=" + row["case"], command)
            self.assertIn("+COMMIT_TOHOST=80001000", command)
            self.assertIn("+NO_FSDB", command)
            self.assertEqual(command[command.index("-cm") + 1], "line+cond+fsm+tgl+branch")
            self.assertEqual(command[command.index("-cm_dir") + 1], str(output / "code.vdb"))
            self.assertEqual(command[command.index("-cm_name") + 1], row["case"])
            self.assertIn("+COMMIT_TRACE=" + str(output / "commit_trace.csv"), command)
            self.assertIn("+VECTOR_TRACE=" + str(output / "vector_trace.csv"), command)

    def test_sealed_json_reads_hashed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text('{"ok":true}')
            expected = runner.digest(path)
            self.assertEqual(runner.read_bound(path, expected), {"ok": True})
            path.write_text('{"ok":false}')
            with self.assertRaises(ValueError):
                runner.read_bound(path, expected)

    def test_preflight_mutations_rejected(self):
        original = self.preflight()
        mutations = []
        for field, value in (("status", "PASS"), ("coverage_admitted", True),
                             ("rtl_changed", True), ("measured_raw_increment", 353)):
            pre = copy.deepcopy(original); pre[field] = value; mutations.append(pre)
        for field, value in (("vl", 1), ("checks", 0), ("expected_vector_instructions", 47),
                             ("expected_vector_bytes", 12287), ("status", "FAIL")):
            pre = copy.deepcopy(original); pre["cases"][0][field] = value; mutations.append(pre)
        pre = copy.deepcopy(original); pre["cases"][0]["symbols"]["tohost"] = 0; mutations.append(pre)
        pre = copy.deepcopy(original); pre["cases"][1] = pre["cases"][0]; mutations.append(pre)
        pre = copy.deepcopy(original); del pre["pins"][str(runner.PRE / "vgap95_div32_bound/input.elf")]; mutations.append(pre)
        for pre in mutations:
            with self.subTest(pre=pre.get("status")), self.assertRaises(ValueError):
                runner.validate_preflight(pre, "div64")
        with self.assertRaises(ValueError):
            runner.validate_preflight(original, "unapproved")

    def test_pin_conflicts_and_missing_inventory_rejected(self):
        with self.assertRaises(ValueError):
            runner.merge_pins({"/a": "a" * 64}, {"/a": "b" * 64})
        for pins in ({}, {"relative": "a" * 64}, {"/a": "bad"}):
            with self.subTest(pins=pins), self.assertRaises(ValueError):
                runner.merge_pins({}, pins)

    def fixture(self, tmp):
        path = Path(tmp) / "input"
        path.write_bytes(b"sealed")
        out = Path(tmp) / "run"
        manifest = dict(case="div64", command=["NEVER_EXECUTED"], pins={str(path): runner.digest(path)})
        return path, out, manifest

    def test_prelaunch_drift_cannot_start(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner.subprocess, "run") as launch:
            path, out, manifest = self.fixture(tmp)
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                runner.run(out, manifest)
            launch.assert_not_called()
            self.assertFalse(out.exists())

    def test_postlaunch_drift_preserves_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, out, manifest = self.fixture(tmp)
            def fake_launch(*args, **kwargs):
                path.write_bytes(b"changed")
                return subprocess.CompletedProcess(args[0], 0)
            with patch.object(runner.subprocess, "run", side_effect=fake_launch):
                with self.assertRaises(ValueError):
                    runner.run(out, manifest)
            status = json.loads((out / "simulation-status.json").read_bytes())
            self.assertEqual(status["status"], "SIMULATION_NOT_ADMITTED")
            self.assertIsNotNone(status["post_failure_pin_error"])
            self.assertTrue((out / "manifest.json").is_file())

    def test_timeout_nonzero_and_mock_success_never_admit(self):
        for result in (subprocess.TimeoutExpired("mock", 600),
                       subprocess.CalledProcessError(1, "mock"), subprocess.CompletedProcess("mock", 0)):
            with tempfile.TemporaryDirectory() as tmp:
                _, out, manifest = self.fixture(tmp)
                kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
                with patch.object(runner.subprocess, "run", **kwargs) as launch:
                    if isinstance(result, Exception):
                        with self.assertRaises(type(result)):
                            runner.run(out, manifest)
                    else:
                        runner.run(out, manifest)
                self.assertEqual(launch.call_args.kwargs["timeout"], 600)
                self.assertTrue(launch.call_args.kwargs["check"])
                status = json.loads((out / "simulation-status.json").read_bytes())
                self.assertFalse(status["coverage_admitted"])
                self.assertFalse(status["admission_performed"])
                self.assertNotEqual(status["status"], "PASS")

    def test_prepare_rejects_existing_or_external_output(self):
        for out in (runner.PRE, Path("/tmp/gap95-not-allowed"), runner.OUT / ".." / "escape"):
            with self.subTest(output=out), self.assertRaises(ValueError):
                runner.prepare("div64", out)


if __name__ == "__main__":
    unittest.main()
