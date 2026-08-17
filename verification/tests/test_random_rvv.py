import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ara_verify.dependencies import DependencyError
from ara_verify.random_rvv import (
    RandomRvvOptions,
    RandomRvvRunOptions,
    _comparison_vector_checkpoint,
    _generated_case_sort_key,
    _link_generator_simv,
    _rewrite_ordered_indexed_stores,
    _rewrite_ordered_fp_reductions,
    _rewrite_reserved_indexed_store_source_overlaps,
    _rewrite_reserved_narrowing_source_overlaps,
    _vector_checkpoint_report,
    random_rvv_command,
    run_random_rvv,
)
from ara_verify.trace import TraceValidationError


class RandomRvvCommandTests(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        tool = root / "verification/tools/riscv-dv-rvv1"
        tool.mkdir(parents=True)
        (tool / "run.py").write_text("", encoding="utf-8")
        (root / "verification/riscv_dv").mkdir(parents=True)
        (root / "verification/riscv_dv/testlist.yaml").write_text("", encoding="utf-8")
        (root / "verification/toolchain.lock.json").write_text(json.dumps({
            "schema_version": 1,
            "tools": {
                "riscv-dv-rvv1": {
                    "url": "https://example.com/riscv-dv.git",
                    "fetch_ref": "refs/pull/1/head",
                    "revision": "0123456789abcdef0123456789abcdef01234567",
                    "path": "verification/tools/riscv-dv-rvv1",
                }
            },
        }), encoding="utf-8")
        return root

    def test_generated_cases_are_sorted_by_numeric_suffix(self):
        paths = [
            Path("profile_10.S"),
            Path("profile_2.S"),
            Path("profile_49.S"),
            Path("profile_1.S"),
            Path("profile_0.S"),
        ]

        self.assertEqual(
            [path.name for path in sorted(paths, key=_generated_case_sort_key)],
            ["profile_0.S", "profile_1.S", "profile_2.S", "profile_10.S", "profile_49.S"],
        )

    @mock.patch("ara_verify.random_rvv.subprocess.run")
    def test_precompiled_generator_uses_simulation_only_and_is_linked(
        self, run: mock.Mock
    ):
        run.return_value = subprocess.CompletedProcess(
            [], 0, "0123456789abcdef0123456789abcdef01234567\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory))
            generator = root / "shared/vcs_simv"
            generator.parent.mkdir()
            generator.write_bytes(b"generator")
            (generator.parent / "vcs_simv.daidir").mkdir()
            output = root / "profile"
            output.mkdir()

            _link_generator_simv(output, generator)
            command = random_rvv_command(RandomRvvOptions(
                repo_root=root,
                test="profile",
                iterations=1,
                seed=1,
                output=output,
            ), simulate_only=True)

            self.assertTrue((output / "vcs_simv").is_symlink())
            self.assertEqual((output / "vcs_simv").resolve(), generator.resolve())
            self.assertTrue((output / "vcs_simv.daidir").is_symlink())
            self.assertEqual(
                (output / "vcs_simv.daidir").resolve(),
                (generator.parent / "vcs_simv.daidir").resolve(),
            )
            self.assertIn("--so", command)

    def test_precompiled_generator_rejects_conflicting_output_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = root / "shared_simv"
            generator.write_bytes(b"generator")
            (root / "shared_simv.daidir").mkdir()
            output = root / "profile"
            output.mkdir()
            (output / "vcs_simv").write_bytes(b"other")

            with self.assertRaisesRegex(RuntimeError, "does not match"):
                _link_generator_simv(output, generator)

    def test_precompiled_generator_requires_vcs_runtime_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = root / "shared/vcs_simv"
            generator.parent.mkdir()
            generator.write_bytes(b"generator")
            output = root / "profile"
            output.mkdir()

            with self.assertRaisesRegex(DependencyError, "runtime database"):
                _link_generator_simv(output, generator)

    def test_strict_random_rewrites_only_unordered_fp_reduction_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "profile_0.S"
            source.write_text(
                "  vfredusum.vs v1, v2, v3\n"
                "\tvfwredusum.vs v4, v8, v6, v0.t\n"
                "  vfredosum.vs v7, v9, v10\n"
                "# vfredusum.vs in a comment must remain unchanged\n",
                encoding="utf-8",
            )

            rewrites = _rewrite_ordered_fp_reductions(source)

            self.assertEqual(rewrites, {
                "vfredusum.vs": 1,
                "vfwredusum.vs": 1,
            })
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "  vfredosum.vs v1, v2, v3\n"
                "\tvfwredosum.vs v4, v8, v6, v0.t\n"
                "  vfredosum.vs v7, v9, v10\n"
                "# vfredusum.vs in a comment must remain unchanged\n",
            )

    def test_strict_random_rewrites_unordered_indexed_stores_only(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "profile_0.S"
            source.write_text(
                "  vsuxei32.v v4, (a0), v8\n"
                "\tvsuxseg4ei64.v v16, (a1), v24, v0.t\n"
                "  vsoxei16.v v2, (a2), v6\n"
                "  vluxseg2ei32.v v10, (a3), v12\n"
                "# vsuxei8.v in a comment must remain unchanged\n",
                encoding="utf-8",
            )

            rewrites = _rewrite_ordered_indexed_stores(source)

            self.assertEqual(rewrites, {"vsuxei": 1, "vsuxseg": 1})
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "  vsoxei32.v v4, (a0), v8\n"
                "\tvsoxseg4ei64.v v16, (a1), v24, v0.t\n"
                "  vsoxei16.v v2, (a2), v6\n"
                "  vluxseg2ei32.v v10, (a3), v12\n"
                "# vsuxei8.v in a comment must remain unchanged\n",
            )

    def test_strict_random_repairs_reserved_narrowing_source_eew_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "profile_0.S"
            source.write_text(
                "  vsetvli zero, a0, e32, m2, tu, mu\n"
                "  vnsrl.wv v28, v28, v30\n"
                "  vnsra.wv v4, v8, v12\n"
                "  vsetivli zero, 7, e16, m1, ta, ma\n"
                "  vnclipu.wv v4, v4, v4, v0.t\n"
                "  vsetvli zero, a1, e8, mf2, ta, ma\n"
                "  vnclip.wv v8, v8, v8\n",
                encoding="utf-8",
            )

            rewrites = _rewrite_reserved_narrowing_source_overlaps(source)

            self.assertEqual(rewrites, {
                "vnsrl.wv": 1,
                "vnsra.wv": 0,
                "vnclipu.wv": 1,
                "vnclip.wv": 1,
            })
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "  vsetvli zero, a0, e32, m2, tu, mu\n"
                "  vnsrl.wv v28, v28, v0\n"
                "  vnsra.wv v4, v8, v12\n"
                "  vsetivli zero, 7, e16, m1, ta, ma\n"
                "  vnclipu.wv v4, v4, v1, v0.t\n"
                "  vsetvli zero, a1, e8, mf2, ta, ma\n"
                "  vnclip.wv v8, v8, v0\n",
            )

    def test_strict_random_repairs_reserved_indexed_store_source_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "profile_0.S"
            source.write_text(
                "  vsetvli zero, a0, e64, m8, tu, mu\n"
                "  vsoxei32.v v16, (sp), v20\n"
                "  vsoxei64.v v16, (sp), v20\n"
                "  vsetivli zero, 31, e16, m4, ta, ma\n"
                "  vsoxei32.v v8, (a0), v8, v0.t\n",
                encoding="utf-8",
            )

            rewrites = _rewrite_reserved_indexed_store_source_overlaps(source)

            self.assertEqual(rewrites, {"indexed_store_source_overlap": 2})
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "  vsetvli zero, a0, e64, m8, tu, mu\n"
                "  nop  # removed reserved dual-EEW indexed store: "
                "vsoxei32.v v16, (sp), v20\n"
                "  vsoxei64.v v16, (sp), v20\n"
                "  vsetivli zero, 31, e16, m4, ta, ma\n"
                "  nop  # removed reserved dual-EEW indexed store: "
                "vsoxei32.v v8, (a0), v8, v0.t\n",
            )

    def test_strict_random_repairs_reserved_indexed_segment_store_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "profile_0.S"
            source.write_text(
                "  vsetvli zero, a0, e64, m2, tu, mu\n"
                "  vsoxseg3ei32.v v8, (a0), v12\n",
                encoding="utf-8",
            )

            rewrites = _rewrite_reserved_indexed_store_source_overlaps(source)

            self.assertEqual(rewrites, {"indexed_store_source_overlap": 1})
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "  vsetvli zero, a0, e64, m2, tu, mu\n"
                "  nop  # removed reserved dual-EEW indexed store: "
                "vsoxseg3ei32.v v8, (a0), v12\n",
            )

    def test_strict_random_decodes_constant_vsetvl_for_narrowing_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "profile_0.S"
            source.write_text(
                "  li x22, 0x81\n"  # e8,m2,tu,ma
                "  vsetvl zero, zero, s6\n"
                "  vnclip.wv v24, v12, v30\n"
                "  vnclipu.wv v24, v12, v14, v0.t\n",
                encoding="utf-8",
            )

            rewrites = _rewrite_reserved_narrowing_source_overlaps(source)

            self.assertEqual(rewrites["vnclip.wv"], 0)
            self.assertEqual(rewrites["vnclipu.wv"], 1)
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "  li x22, 0x81\n"
                "  vsetvl zero, zero, s6\n"
                "  vnclip.wv v24, v12, v30\n"
                "  vnclipu.wv v24, v12, v2, v0.t\n",
            )

    def test_strict_random_rejects_unproven_vsetvl_for_narrowing_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "profile_0.S"
            source.write_text(
                "  addi s6, a0, 1\n"
                "  vsetvl zero, zero, s6\n"
                "  vnclip.wv v24, v12, v14\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "cannot prove vsetvl vtype"):
                _rewrite_reserved_narrowing_source_overlaps(source)

    @mock.patch("ara_verify.random_rvv.subprocess.run")
    def test_single_seed_command(self, run: mock.Mock):
        run.return_value = subprocess.CompletedProcess([], 0, "0123456789abcdef0123456789abcdef01234567\n")
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory))
            command = random_rvv_command(RandomRvvOptions(
                repo_root=root,
                test="ara_dsa_rvv1_smoke",
                iterations=1,
                seed=7,
                output=root / "out",
            ))
            self.assertIn("rv64gcv", command)
            self.assertEqual(command[command.index("--gen_timeout") + 1], "900")
            self.assertEqual(command[command.index("--batch_size") + 1], "5")
            self.assertEqual(command[-2:], ["--seed", "7"])

    @mock.patch("ara_verify.random_rvv.subprocess.run")
    def test_multi_seed_command(self, run: mock.Mock):
        run.return_value = subprocess.CompletedProcess([], 0, "0123456789abcdef0123456789abcdef01234567\n")
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory))
            command = random_rvv_command(RandomRvvOptions(
                repo_root=root,
                test="ara_dsa_rvv1_arithmetic",
                iterations=3,
                seed=11,
                output=root / "out",
            ))
            self.assertEqual(command[-4:], ["--iterations", "3", "--start_seed", "11"])

    @mock.patch("ara_verify.random_rvv.subprocess.run")
    def test_profile_iteration_command_keeps_yaml_count(self, run: mock.Mock):
        run.return_value = subprocess.CompletedProcess([], 0, "0123456789abcdef0123456789abcdef01234567\n")
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory))
            command = random_rvv_command(RandomRvvOptions(
                repo_root=root,
                test="ara_dsa_rvv1_arithmetic",
                iterations=None,
                seed=21,
                output=root / "out",
            ))
            self.assertEqual(command[-2:], ["--start_seed", "21"])

    @mock.patch("ara_verify.random_rvv.subprocess.run")
    def test_compile_steps(self, run: mock.Mock):
        run.return_value = subprocess.CompletedProcess([], 0, "0123456789abcdef0123456789abcdef01234567\n")
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory))
            command = random_rvv_command(RandomRvvOptions(
                repo_root=root,
                test="ara_dsa_rvv1_smoke",
                iterations=1,
                seed=3,
                output=root / "out",
            ), steps="gen,gcc_compile")
            self.assertEqual(command[command.index("--steps") + 1], "gen,gcc_compile")

    def test_final_status_gate_precedence(self):
        scenarios = [
            ("spike failure", 1, False, 0, False, "success", "MATCH", "valid", "PASS",
             "SPIKE_FAIL"),
            ("rtl timeout", 0, False, 0, True, "success", "MATCH", "valid", "PASS",
             "RTL_TIMEOUT"),
            ("commit watchdog", 0, False, 1, False, "watchdog", "MATCH", "valid", "PASS",
             "RTL_STALL"),
            ("rtl failure", 0, False, 1, False, "failure", "MATCH", "valid", "PASS",
             "RTL_FAIL"),
            ("scalar mismatch", 0, False, 0, False, "success", "MISMATCH", "valid", "PASS",
             "MISMATCH"),
            ("invalid trace", 0, False, 0, False, "success", "MATCH", "error", "PASS",
             "TRACE_FAIL"),
            ("vector mismatch", 0, False, 0, False, "success", "MATCH", "valid",
             "MISMATCH", "VECTOR_MISMATCH"),
            ("matched scalar cannot accept vector prefix", 0, False, 0, False,
             "success", "MATCH", "valid", "PREFIX", "VECTOR_MISMATCH"),
            ("shared unobservable prefix", 0, False, 0, False, "success", "PREFIX",
             "valid", "PREFIX", "PASS"),
            ("all gates pass", 0, False, 0, False, "success", "MATCH", "valid", "PASS",
             "PASS"),
        ]

        for (name, spike_rc, spike_timeout, rtl_rc, rtl_timeout, rtl_log,
             comparison_status, trace_status, vector_status, expected) in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                output = root / "out"
                (output / "asm_test").mkdir(parents=True)
                (output / "asm_test/profile_0.S").write_text(
                    "  vsetvli t0, a0, e32, m1, ta, ma\n"
                    "  vsuxei32.v v4, (a0), v8\n",
                    encoding="utf-8",
                )
                (output / "asm_test/profile_0.o").write_bytes(b"elf")
                tool = root / "tool/run.py"
                tool.parent.mkdir(parents=True)
                tool.write_text("")
                for relative in (
                    "install/riscv-gcc/bin/riscv64-unknown-elf-gcc",
                    "install/riscv-gcc/bin/riscv64-unknown-elf-objcopy",
                    "install/riscv-gcc/bin/riscv64-unknown-elf-readelf",
                    "install/riscv-llvm/bin/llvm-objdump",
                    "simv",
                    "spike",
                ):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"tool")

                options = RandomRvvRunOptions(
                    generation=RandomRvvOptions(
                        repo_root=root,
                        test="profile",
                        iterations=1,
                        seed=6,
                        output=output,
                    ),
                    simv=root / "simv",
                    spike=root / "spike",
                    vector_commit_compare=True,
                )

                def run_logged(*args, **kwargs):
                    run_logged.calls += 1
                    if run_logged.calls <= 2:
                        return 0, 0.1, False
                    return spike_rc, 0.2, spike_timeout

                run_logged.calls = 0

                def run_rtl(command, case, log_path, timeout_s):
                    text = {
                        "success": "Core Test *** SUCCESS ***\n",
                        "watchdog": "commit watchdog expired\n",
                        "failure": "Core Test *** FAILED ***\n",
                    }[rtl_log]
                    log_path.write_text(text)
                    return rtl_rc, 0.3, rtl_timeout

                def validate_trace(_path):
                    if trace_status == "error":
                        raise TraceValidationError("incomplete trace")
                    return {"records": 1}

                with (
                    mock.patch("ara_verify.random_rvv.random_rvv_command",
                               return_value=["python3", str(tool)]),
                    mock.patch("ara_verify.random_rvv._run_logged", side_effect=run_logged),
                    mock.patch("ara_verify.random_rvv._run_rtl", side_effect=run_rtl),
                    mock.patch("ara_verify.random_rvv.write_stimulus_coverage"),
                    mock.patch("ara_verify.random_rvv._elf_entry", return_value=0x80000000),
                    mock.patch("ara_verify.random_rvv._elf_symbol", return_value=0x80001000),
                    mock.patch("ara_verify.random_rvv.compare_commit_prefix",
                               return_value={"status": comparison_status}),
                    mock.patch("ara_verify.random_rvv.validate_trace",
                               side_effect=validate_trace),
                    mock.patch("ara_verify.random_rvv.compare_vector_commits",
                               return_value={"status": vector_status}),
                ):
                    returncode = run_random_rvv(options)

                result = json.loads((output / "summary.json").read_text())[0]
                self.assertEqual(result["status"], expected)
                self.assertEqual(returncode, 0 if expected == "PASS" else 1)
                self.assertIn(
                    "vsoxei32.v", (output / "asm_test/profile_0.S").read_text()
                )
                self.assertIn(
                    "e32, m1, tu, mu", (output / "asm_test/profile_0.S").read_text()
                )
                rewrite_manifest = json.loads(
                    (output / "deterministic_rewrite_manifest.json").read_text()
                )
                self.assertEqual(
                    rewrite_manifest[0]["ordered_indexed_store_rewrites"]["vsuxei"], 1
                )
                self.assertEqual(rewrite_manifest[0]["policy_rewrites"], 1)

    def test_locates_vector_checkpoint_from_mismatch_pc(self):
        comparison = {
            "mismatch": {
                "ara": {"pc": "0x0000000080002274"},
                "spike": {"pc": "0x0000000080002274"},
            }
        }
        locations = [
            {"index": 0, "site": "initial_state", "read_loop_pc": "0x00000000800020b2"},
            {"index": 1, "site": "vwaddu.wx", "read_loop_pc": "0x0000000080002274"},
        ]

        self.assertEqual(_comparison_vector_checkpoint(comparison, locations), locations[1])

    def test_vector_checkpoint_location_requires_matching_pc(self):
        comparison = {"mismatch": {"ara": {"pc": "0x0000000080004000"}}}

        self.assertIsNone(_comparison_vector_checkpoint(comparison, []))

    def test_reports_each_checkpoint_around_first_failure(self):
        locations = [
            {
                "index": 0,
                "site": "initial_state",
                "checkpoint_pc": "0x0000000080002000",
                "read_loop_pc": "0x0000000080002100",
                "read_done_pc": "0x0000000080002110",
            },
            {
                "index": 1,
                "site": "vadd.vv v2, v0, v1",
                "instruction_pc": "0x0000000080002120",
                "checkpoint_pc": "0x0000000080002124",
                "read_loop_pc": "0x0000000080002200",
                "read_done_pc": "0x0000000080002210",
            },
            {
                "index": 2,
                "site": "vmul.vv v4, v2, v3",
                "instruction_pc": "0x0000000080002220",
                "checkpoint_pc": "0x0000000080002224",
                "read_loop_pc": "0x0000000080002300",
                "read_done_pc": "0x0000000080002310",
            },
        ]
        comparison = {
            "status": "MISMATCH",
            "mismatch": {
                "spike": {"pc": "0x0000000080002200"},
                "ara": {"pc": "0x0000000080002200"},
            },
        }

        report = _vector_checkpoint_report(comparison, locations)

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["passed"], 1)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["not_run"], 1)
        self.assertEqual(
            [checkpoint["status"] for checkpoint in report["checkpoints"]],
            ["PASS", "FAIL", "NOT_RUN"],
        )

    def test_reports_all_checkpoints_passed_on_full_match(self):
        locations = [
            {"index": 0, "site": "initial_state"},
            {"index": 1, "site": "vadd.vv v2, v0, v1"},
        ]

        report = _vector_checkpoint_report({"status": "MATCH"}, locations)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["passed"], 2)
        self.assertEqual(report["failed"], 0)

    def test_reports_completed_matching_prefix_as_passed(self):
        locations = [
            {"index": 0, "site": "initial_state"},
            {"index": 1, "site": "vadd.vv v2, v0, v1"},
        ]

        report = _vector_checkpoint_report(
            {"status": "PREFIX"}, locations, completed=True
        )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["passed"], 2)

    def test_reports_incomplete_matching_prefix_as_unresolved(self):
        locations = [{"index": 0, "site": "initial_state"}]

        report = _vector_checkpoint_report(
            {"status": "PREFIX"}, locations, completed=False
        )

        self.assertEqual(report["status"], "UNRESOLVED")
        self.assertEqual(report["unknown"], 1)
