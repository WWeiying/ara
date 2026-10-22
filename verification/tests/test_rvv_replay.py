import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from ara_verify.artifacts import check_inputs
from ara_verify.rvv_replay import (
    RvvReplayCase,
    RvvReplayOptions,
    _freeze_replay_inputs,
    failed_random_cases,
    _replay_comparison_status,
    _rtl_setup_error,
    _run_case,
)


class RvvReplaySetupTests(unittest.TestCase):
    def test_reference_timeout_never_calls_parsers_and_preserves_rtl_fatal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("input.elf", "spike", "simv"):
                (root / name).write_bytes(b"fixture")
            options = RvvReplayOptions(root / "out", root / "simv", root / "spike", 1, 1, 1)
            replay = RvvReplayCase("case", "profile", 1, "TIMEOUT", root / "input.elf")

            def rtl(command, case, log, timeout):
                log.write_text("Fatal: AXI read address exceeds simulation L2\n")
                return 1, 0.1, False

            with (mock.patch("ara_verify.rvv_replay._elf_entry", return_value=0x80000000),
                  mock.patch("ara_verify.rvv_replay._elf_symbol", return_value=0x80001000),
                  mock.patch("ara_verify.rvv_replay._optional_vector_exit_pc", return_value=None),
                  mock.patch("ara_verify.rvv_replay._run_logged", return_value=(-9, 60, True)),
                  mock.patch("ara_verify.rvv_replay._run_rtl", side_effect=rtl),
                  mock.patch("ara_verify.rvv_replay.validate_trace", return_value={}),
                  mock.patch("ara_verify.rvv_replay.unobservable_vector_scalar_write_indices") as unknown,
                  mock.patch("ara_verify.rvv_replay.compare_commit_prefix") as scalar,
                  mock.patch("ara_verify.rvv_replay.compare_vector_commits") as vector):
                result = _run_case(options, replay)
            unknown.assert_not_called()
            scalar.assert_not_called()
            vector.assert_not_called()
            self.assertEqual(result["status"], "SPIKE_FAIL")
            self.assertEqual(result["comparison"]["status"], "SKIPPED_REFERENCE_FAILURE")
            self.assertEqual(result["vector_commit"]["status"], "SKIPPED_REFERENCE_FAILURE")
            self.assertEqual(result["rtl_returncode"], 1)
            self.assertIn("Fatal", result["rtl_failure_lines"][0])

    def test_fault_vstart_probe_is_opt_in(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), TemporaryDirectory() as directory:
                root = Path(directory)
                for name in ("input.elf", "spike", "simv"):
                    (root / name).write_bytes(b"fixture")
                options = RvvReplayOptions(
                    root / "out", root / "simv", root / "spike", 1, 1, 1,
                    fault_vstart_probe=enabled)
                replay = RvvReplayCase("case", "profile", 1, "TIMEOUT", root / "input.elf")

                def rtl(command, case, log, timeout):
                    log.write_text("")
                    return 0, 0.1, False

                with (mock.patch("ara_verify.rvv_replay._elf_entry", return_value=0x80000000),
                      mock.patch("ara_verify.rvv_replay._elf_symbol", return_value=0x80001000),
                      mock.patch("ara_verify.rvv_replay._optional_vector_exit_pc", return_value=None),
                      mock.patch("ara_verify.rvv_replay._run_logged", return_value=(-9, 60, True)),
                      mock.patch("ara_verify.rvv_replay._run_rtl", side_effect=rtl) as run_rtl,
                      mock.patch("ara_verify.rvv_replay.validate_trace", return_value={})):
                    _run_case(options, replay)
                command = run_rtl.call_args.args[0]
                self.assertEqual("+ARA_FAULT_VSTART_PROBE" in command, enabled)

    def test_probe_evidence_is_forwarded_to_both_comparators(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), TemporaryDirectory() as directory:
                root = Path(directory)
                for name in ("input.elf", "spike", "simv"):
                    (root / name).write_bytes(b"fixture")
                options = RvvReplayOptions(
                    root / "out", root / "simv", root / "spike", 1, 1, 1,
                    fault_vstart_probe=enabled)
                replay = RvvReplayCase("case", "profile", 1, "TIMEOUT", root / "input.elf")

                def rtl(command, case, log, timeout):
                    log.write_text("Core Test *** SUCCESS ***\n")
                    (case / "trace_hart_0.log").write_text("")
                    return 0, 0.1, False

                with (mock.patch("ara_verify.rvv_replay._elf_entry", return_value=0x80000000),
                      mock.patch("ara_verify.rvv_replay._elf_symbol", return_value=0x80001000),
                      mock.patch("ara_verify.rvv_replay._optional_vector_exit_pc", return_value=None),
                      mock.patch("ara_verify.rvv_replay._run_logged", return_value=(0, 0.1, False)),
                      mock.patch("ara_verify.rvv_replay._run_rtl", side_effect=rtl),
                      mock.patch("ara_verify.rvv_replay.validate_trace", return_value={}),
                      mock.patch("ara_verify.rvv_replay.unobservable_vector_scalar_write_indices", return_value=set()),
                      mock.patch("ara_verify.rvv_replay.compare_commit_prefix", return_value={"status": "TERMINAL_MATCH"}) as scalar,
                      mock.patch("ara_verify.rvv_replay.compare_vector_commits", return_value={"status": "PASS"}) as vector):
                    result = _run_case(options, replay)
                self.assertEqual(result["status"], "PASS")
                case = root / "out/tests/case"
                probe = case / "run.vcs.log" if enabled else None
                self.assertEqual(scalar.call_args.kwargs["fault_probe_log"], probe)
                self.assertEqual(vector.call_args.kwargs["fault_probe_log"], probe)
                self.assertEqual(scalar.call_args.kwargs["fault_vector_trace"],
                                 case / "ara_vector_trace.csv" if enabled else None)

    def test_replay_passed_cases_requires_explicit_selection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            summary.write_text(json.dumps([
                {"name": "passed", "profile": "load_store_slide", "seed": 71,
                 "status": "PASS", "elf": str(root / "passed.elf")},
                {"name": "failed", "profile": "load_store_slide", "seed": 72,
                 "status": "TRACE_FAIL", "elf": str(root / "failed.elf")},
            ]), encoding="utf-8")
            self.assertEqual([case.name for case in failed_random_cases(summary)],
                             ["failed"])
            self.assertEqual([case.name for case in failed_random_cases(
                summary, include_passed=True)], ["passed", "failed"])
            self.assertEqual([case.name for case in failed_random_cases(
                summary, ["passed"], include_passed=True)], ["passed"])
            with self.assertRaisesRegex(ValueError, "not found"):
                failed_random_cases(summary, ["passed"])

    def test_empty_replay_selection_is_an_error(self):
        with TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.json"
            summary.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no replayable"):
                failed_random_cases(summary, include_passed=True)

    def test_prefix_cannot_pass_strict_replay(self):
        self.assertEqual(_replay_comparison_status(
            {"status": "PREFIX"}, {"status": "PASS"}), "INCOMPLETE_PREFIX")
        self.assertEqual(_replay_comparison_status(
            {"status": "PREFIX"}, {"status": "PREFIX"}), "INCOMPLETE_PREFIX")

    def test_terminal_match_requires_complete_vector_comparison(self):
        self.assertEqual(_replay_comparison_status(
            {"status": "TERMINAL_MATCH"}, {"status": "PREFIX"}), "VECTOR_INCOMPLETE")
        self.assertEqual(_replay_comparison_status(
            {"status": "TERMINAL_MATCH"}, {"status": "PASS"}), "PASS")

    def test_generator_simulator_fatal_is_not_dut_failure(self):
        self.assertTrue(_rtl_setup_error(
            "UVM_FATAL @ 0: reporter [NOCOMP] No components instantiated."
        ))

    def test_dut_failure_is_not_setup_failure(self):
        self.assertFalse(_rtl_setup_error("Core Test *** FAILED ***"))
        self.assertFalse(_rtl_setup_error("UVM_FATAL @ 400: reporter [CHECKER] mismatch"))

    def test_replay_freezes_elf_and_full_simulator_image(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.elf"
            source.write_bytes(b"original")
            simv = root / "simv"
            simv.write_bytes(b"launcher")
            libraries = root / "simv.daidir"
            libraries.mkdir()
            (libraries / "design.so").write_bytes(b"design")
            spike = root / "spike"
            spike.write_bytes(b"reference")
            case = root / "case"
            case.mkdir()
            options = RvvReplayOptions(root, simv, spike, 1, 1, 1)
            replay = RvvReplayCase("case", "profile", 1, "RTL_TIMEOUT", source)

            frozen, inputs = _freeze_replay_inputs(options, replay, case)
            self.assertEqual(frozen.read_bytes(), b"original")
            self.assertEqual(check_inputs(inputs, frozen), [])
            source.write_bytes(b"changed")
            self.assertEqual(frozen.read_bytes(), b"original")
            (libraries / "design.so").write_bytes(b"changed")
            self.assertIn("simulator executable or generated RTL libraries changed",
                          check_inputs(inputs, frozen))
