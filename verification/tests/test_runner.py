import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ara_verify.model import TestCase as CaseSpec, TestResult as CaseResult
from ara_verify.runner import (
    FAIL_RE,
    SUCCESS_RE,
    RegressionRunner,
    RunOptions,
    _safe_name,
)
from verify import _parser


class ResultParsingTests(unittest.TestCase):
    def test_success_marker(self):
        self.assertIsNotNone(SUCCESS_RE.search("Core Test *** SUCCESS *** (tohost = 0)"))

    def test_failure_markers(self):
        for text in (
            "Core Test *** FAILED ***",
            "UVM_FATAL",
            "UVM_FATAL /path/monitor.sv(42) @ 1000: actual failure",
            "UVM_FATAL :    1",
            "Error: assertion foo failed",
            "Index 0 FAILED. Got 0, expected 1.",
            "FAILED.",
        ):
            self.assertIsNotNone(FAIL_RE.search(text))

    def test_zero_uvm_fatal_summary_is_not_a_failure(self):
        self.assertIsNone(FAIL_RE.search("UVM_FATAL :    0\n"))

    def test_vcs_warning_assertion_is_not_a_fatal_failure(self):
        warning = (
            "gen_assertion[1].a_invalid_read_data: started at 10fs failed at 10fs\n"
            "Warning: reading invalid data"
        )
        self.assertIsNone(FAIL_RE.search(warning))

    def test_safe_name(self):
        self.assertEqual(_safe_name("rvv:vadd/test"), "rvv_vadd_test")

    def test_run_timeout_override(self):
        args = _parser().parse_args(["run", "rvv-directed", "--timeout", "900"])

        self.assertEqual(args.timeout, 900)

    def test_code_coverage_requires_private_instrumented_build(self):
        args = _parser().parse_args(["run", "smoke", "--code-coverage"])
        self.assertTrue(args.code_coverage)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            options = RunOptions(
                repo_root=Path(__file__).resolve().parents[2],
                output_root=root / "result", config="default",
                jobs=1, seed=1, dry_run=True, build_only=False,
                skip_build=False, simv=None, commit_trace=False,
                timeout_s=None, code_coverage=True,
            )
            runner = RegressionRunner(options, [], ["verify.py", "run"])
            self.assertIn("code_coverage=1", runner._build_commands()[1])
            self.assertIn("verify_source_manifest=1", runner._build_commands()[1])
            runner.prepare()
            self.assertTrue(json.loads((root / "result/run.json").read_text())["code_coverage"])
            case = CaseSpec("rvv:vadd", "rvv", "unused", root / "unused.elf", "vadd", 60)
            result = runner._run_test(case, root / "simv")
            self.assertEqual(result.status, "DRY_RUN")
            command = json.loads((result.artifact_dir / "command.json").read_text())["command"]
            self.assertIn(str(root / "result/tests/rvv_vadd/work/code.vdb"), command)
            self.assertIn("rvv_vadd", command)
            with self.assertRaisesRegex(ValueError, "fresh instrumented"):
                RegressionRunner(replace(options, skip_build=True), [], []).prepare()

    def test_reused_simv_build_uses_matching_l2_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            simv = root / "sim/simv"
            simv.parent.mkdir()
            simv.touch()
            config = simv.parent / "simulator.conf"
            config.write_text("sim_l2_mb=4\nsim_l2_bytes=4194304\n")
            options = RunOptions(
                repo_root=Path(__file__).resolve().parents[2],
                output_root=root / "result", config="default", jobs=1, seed=1,
                dry_run=True, build_only=False, skip_build=False, simv=simv,
                commit_trace=False, timeout_s=None,
            )
            runner = RegressionRunner(options, [], ["verify.py", "run"])
            self.assertIn("sim_l2_mb=4", runner._build_commands()[0])
            config.write_text("sim_l2_mb=4\nsim_l2_bytes=1048576\n")
            with self.assertRaisesRegex(RuntimeError, "inconsistent L2 size"):
                runner._build_commands()

    def test_suite_freezes_all_binaries_before_releasing_app_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            simv = root / "sim/simv"
            simv.parent.mkdir()
            simv.touch()
            (simv.parent / "simulator.conf").write_text(
                "sim_l2_mb=4\nsim_l2_bytes=4194304\n")
            (root / "hardware").mkdir()
            (root / "hardware/Makefile").write_text("")
            programs = [root / "apps/bin/first", root / "apps/bin/second"]
            tests = [CaseSpec(name, "app", f"bin/{name}", binary, name, 60)
                     for name, binary in zip(("first", "second"), programs)]
            options = RunOptions(
                repo_root=root, output_root=root / "out", config="default",
                jobs=2, seed=1, dry_run=False, build_only=False,
                skip_build=False, simv=simv, commit_trace=False, timeout_s=None,
            )
            runner = RegressionRunner(options, tests, ["verify.py", "run"])

            def build_apps(command, cwd, log_path):
                for index, binary in enumerate(programs):
                    binary.parent.mkdir(parents=True, exist_ok=True)
                    binary.write_bytes(f"version-1-{index}".encode())

            with patch("ara_verify.runner._run_logged", side_effect=build_apps):
                self.assertEqual(runner.build(), simv.resolve())
            for binary in programs:
                binary.write_bytes(b"version-2")
            for index, test in enumerate(tests):
                snapshot = root / "out/tests" / test.name / "input.elf"
                self.assertEqual(snapshot.read_bytes(), f"version-1-{index}".encode())
                self.assertEqual(runner._frozen_binaries[test.name],
                                 hashlib.sha256(snapshot.read_bytes()).hexdigest())

    def test_missing_binary_cannot_join_suite_after_freeze(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "apps/bin/late"
            test = CaseSpec("late", "app", "bin/late", binary, "late", 60)
            options = RunOptions(
                repo_root=root, output_root=root / "out", config="default",
                jobs=1, seed=1, dry_run=False, build_only=False,
                skip_build=True, simv=None, commit_trace=False, timeout_s=None,
            )
            runner = RegressionRunner(options, [test], ["verify.py", "run"])
            runner._freeze_programs_locked()
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"arrived too late")
            result = runner._run_test(test, root / "simv")
            self.assertEqual(result.status, "ERROR")
            self.assertEqual(result.reason, "binary is missing")
            self.assertFalse((root / "out/tests/late/input.elf").exists())

    def test_report_completion_updates_run_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            options = RunOptions(
                repo_root=output,
                output_root=output,
                config="default",
                jobs=1,
                seed=1,
                dry_run=False,
                build_only=False,
                skip_build=True,
                simv=None,
                commit_trace=False,
                timeout_s=None,
            )
            runner = RegressionRunner(options, [], ["verify.py", "run"])
            runner.prepare()
            self.assertEqual(json.loads((output / "run.json").read_text())["status"], "RUNNING")

            runner._write_reports([
                CaseResult("rvv:test", "rvv", "PASS", 0, 1.0, "", output / "case")
            ])

            metadata = json.loads((output / "run.json").read_text())
            self.assertEqual(metadata["status"], "COMPLETE")
            self.assertEqual(metadata["status_counts"], {"PASS": 1})
            self.assertIn("completed_at", metadata)
