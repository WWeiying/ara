"""Host-only SoC input/ELF tests. No RTL simulator is invoked."""

import struct
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fpga import run_soc_smoke as runner

HAS_ELFTOOLS = importlib.util.find_spec("elftools") is not None


def fixture_elf(*, entry=0x80000000, machine=243, memsz=16, filesz=4, addr=0x80000000):
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    header = ident + struct.pack("<HHIQQQIHHHHHH", 2, machine, 1, entry, 64, 0, 0,
                                 64, 56, 1, 0, 0, 0)
    phdr = struct.pack("<IIQQQQQQ", 1, 5, 0x100, addr, addr, filesz, memsz, 0x100)
    return (header + phdr).ljust(0x100, b"\0") + bytes([0x13, 0, 0, 0])


class SocSmokeTests(unittest.TestCase):
    def test_seal_rejects_duplicate_and_traversal(self):
        line = "a" * 64 + "  rtl/a.sv\n"
        self.assertEqual(runner.seal(line.encode()), {"rtl/a.sv": "a" * 64})
        for bad in (line + line, line.replace("rtl/a.sv", "../x"), "bad\n", ""):
            with self.assertRaises(ValueError):
                runner.seal(bad.encode())

    def test_safe_filenames(self):
        for value in ("../x", "/x", "a//b", "a/./b", "a+b", "x y", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.safe_name(value)

    def test_exact_board_function_copy(self):
        body = ("  function automatic cheshire_cfg_t board_cfg();\n"
                "    cheshire_cfg_t cfg = DefaultCfg;\n"
                "    cfg.NumCores = 1;\n    return cfg;\n  endfunction")
        self.assertTrue(runner.board_config("module x;\n" + body + "\nendmodule").endswith(body + "\n"))
        for source in ("", body + body):
            with self.assertRaises(ValueError):
                runner.board_config(source)

    def test_vcs_typedef_adapter_moves_only_ara_types(self):
        source = (
            "module cheshire_soc;\n  `CHESHIRE_TYPEDEF_ALL(, Cfg)\n"
            "  for (genvar i = 0; i < NumIntHarts; i++) begin : gen_cva6_cores\n"
            "    if (Cfg.Ara) begin : gen_ara\n"
            "      // Configure Ara with the right AXI id width\n"
            "      typedef logic [Cfg.AxiMstIdWidth-1:0] ara_id_t;\n"
            "      `AXI_TYPEDEF_ALL(ara, addr_t, ara_id_t, data_t, strb_t, user_t)\n"
            "      axi_ara_wide_req_t  axi_ara_wide_req_inval, axi_ara_wide_req;\n"
            "      assign ready = valid;\n"
            "    end\n  end\nendmodule\n"
        )
        adapted = runner.vcs_compat_cheshire_soc(source)
        self.assertLess(adapted.index("`AXI_TYPEDEF_ALL("), adapted.index("gen_cva6_cores"))
        self.assertIn("      assign ready = valid;", adapted)
        self.assertEqual(adapted.count("`AXI_TYPEDEF_ALL("), 1)
        with self.assertRaises(ValueError):
            runner.vcs_compat_cheshire_soc(adapted)

    def test_vcs_id_map_adapter_preserves_zero_default(self):
        source = (
            "function automatic cva6_id_map_t gen_cva6_id_map(cheshire_cfg_t cfg);\n"
            "    localparam int unsigned DefaultMapEntry[2] = '{0, 0};\n"
            "    case (cfg.AxiMstIdWidth)\n"
            "      default: return '{default: DefaultMapEntry};\n"
            "    endcase\nendfunction\n"
        )
        adapted = runner.vcs_compat_cheshire_pkg(source)
        self.assertIn("default: return '{" + ", ".join(["'{0, 0}"] * 7) + "};", adapted)
        self.assertNotIn("DefaultMapEntry", adapted)
        with self.assertRaises(ValueError):
            runner.vcs_compat_cheshire_pkg(adapted)

    @unittest.skipUnless(HAS_ELFTOOLS, "use verification/tools/soc-venv/bin/python")
    def test_elf_segment_and_bss(self):
        entry, segments = runner.elf_segments(fixture_elf())
        self.assertEqual(entry, 0x80000000)
        self.assertEqual(segments, [(0x80000000, b"\x13" + bytes(15))])
        self.assertEqual(runner.memory_hex(segments),
                         b"@0000000080000000\n13 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n")

    @unittest.skipUnless(HAS_ELFTOOLS, "use verification/tools/soc-venv/bin/python")
    def test_bad_elf_rejected(self):
        for kwargs in ({"machine": 62}, {"entry": 0x80001000}, {"filesz": 20},
                       {"addr": 0}, {"addr": 0xfffffff0, "memsz": 32},
                       {"memsz": 32 * 1024 * 1024}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                runner.elf_segments(fixture_elf(**kwargs))

    def test_hex_separate_segments_no_gap_initialization(self):
        result = runner.memory_hex([(0x80000000, b"\x13"), (0x80000100, b"\x73")])
        self.assertEqual(result, b"@0000000080000000\n13\n@0000000080000100\n73\n")

    def test_fdt_page_has_deterministic_slack_only(self):
        dtb = bytes.fromhex("d00dfeed0000000a") + b"\x12\x34"
        page = runner.initialized_fdt_page(dtb)
        self.assertEqual(page[:len(dtb)], dtb)
        self.assertEqual(page[len(dtb):], bytes(4096 - len(dtb)))
        self.assertEqual(len(page), runner.FDT_PRELOAD_PAGE_BYTES)
        for invalid in (b"", dtb[:-1], b"BAD!" + dtb[4:],
                        bytes.fromhex("d00dfeed00001001") + bytes(4097 - 8)):
            with self.subTest(invalid_length=len(invalid)), self.assertRaises(ValueError):
                runner.initialized_fdt_page(invalid)

    def test_only_explicit_substitutions(self):
        self.assertEqual(len(runner.OMITTED), 5)
        self.assertNotIn("rtl/cheshire/hw/cheshire_soc.sv", runner.OMITTED)
        self.assertNotIn("rtl/cva6/core/cva6.sv", runner.OMITTED)

    def test_expected_fatal_uses_diagnostic_not_exit_code(self):
        log = (
            "TECH_MODELS_EXPECT_FATAL: collision_rw\n"
            "Fatal: \"tech_models.sv\", 139: at time 15000 ps\n"
            "unsupported SRAM collision ports 0/1 address 0\n"
            "$finish at simulation time 15000\n"
        )
        self.assertTrue(runner.expected_fatal_pass(
            {"returncode": 0}, log, "collision_rw", "unsupported SRAM collision"
        ))
        self.assertTrue(runner.expected_fatal_pass(
            {"returncode": 1}, log, "collision_rw", "unsupported SRAM collision"
        ))
        for record, invalid in (
            ({"returncode": 0}, log.replace("Fatal:", "Info:")),
            ({"returncode": 0}, log.replace("collision_rw", "collision_ww")),
            ({"returncode": 0, "timeout": True}, log),
            ({"returncode": -9}, log),
            ({"returncode": 0}, log + "TECH_MODELS_MISSING_FATAL\n"),
        ):
            with self.subTest(record=record, invalid=invalid):
                self.assertFalse(runner.expected_fatal_pass(
                    record, invalid, "collision_rw", "unsupported SRAM collision"
                ))

    def test_license_wait_is_explicit_and_opt_in(self):
        self.assertEqual(runner.vcs_prefix("vcs", False), ["vcs"])
        self.assertEqual(runner.vcs_prefix("vcs", True), ["vcs", "+vcs+lic+wait"])

    def test_linux_budget_guard_uses_latest_complete_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "console.log"
            log.write_bytes(b"[SOC_PROGRESS] cycle=100 phase=LINUX_RUNNING\n"
                            b"[SOC_PROGRESS] cycle=200 phase=LINUX_RUNNING\n"
                            b"[SOC_PROGRESS] cycle=300")
            self.assertEqual(runner.latest_progress_cycle(log), 200)
            self.assertFalse(runner.budget_infeasible(300, 10, 100, 400))
            self.assertTrue(runner.budget_infeasible(300, 10, 100, 10000))
            self.assertFalse(runner.budget_infeasible(10000, 10, 100, 10000))
            self.assertFalse(runner.budget_infeasible(None, 10, 100, 10000))
            self.assertFalse(runner.budget_infeasible(300, 100, 100, 10000))

    def test_linux_log_monitor_reads_appends_and_split_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "console.log"
            monitor = runner.LinuxLogMonitor(log)
            monitor.update()
            with log.open("wb") as output:
                output.write(b"x" * 70000 + b"\n[SOC_PROGRESS] cycle=10 phase=LINUX")
            monitor.update()
            self.assertIsNone(monitor.progress_cycle)
            with log.open("ab") as output:
                output.write(b"_RUNNING\nKernel pan")
            monitor.update()
            self.assertEqual(monitor.progress_cycle, 10)
            self.assertIsNone(monitor.failure_marker)
            with log.open("ab") as output:
                output.write(b"ic - not syncing\n[SOC_PROGRESS] cycle=20 phase=LINUX_RUNNING\n")
            monitor.update()
            self.assertEqual(monitor.progress_cycle, 20)
            self.assertEqual(monitor.failure_marker, "Kernel panic")
            self.assertEqual(monitor.offset, log.stat().st_size)

    def test_linux_budget_guard_never_changes_default_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            result = runner.execute(["/bin/sh", "-c", "printf 'done\\n'"], run, 2)
            self.assertEqual(result["returncode"], 0)
            self.assertNotIn("budget_infeasible", result)

    def test_linux_budget_guard_stops_only_when_opted_in(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            result = runner.execute(
                ["/bin/sh", "-c", "printf '[SOC_PROGRESS] cycle=100 phase=LINUX_RUNNING\\n'; sleep 5"],
                run, 2, min_cycle_target=100000, budget_check_after=0.05,
                budget_poll_interval=0.05)
            self.assertTrue(result["budget_infeasible"])
            self.assertEqual(result["last_progress_cycle"], 100)
            self.assertEqual(result["min_cycle_target"], 100000)
            self.assertFalse(result.get("timeout", False))

    def test_linux_fail_fast_stops_on_explicit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            result = runner.execute(
                ["/bin/sh", "-c", "printf 'Kernel panic - not syncing\\n'; sleep 5"],
                run, 2, budget_poll_interval=0.05, linux_fail_fast=True)
            self.assertEqual(result["early_failure_marker"], "Kernel panic")
            self.assertFalse(result.get("timeout", False))

    def test_linux_fail_fast_stops_on_cache_assertions(self):
        for marker in ("Fatal:", "a_invalid_read_data", "a_invalid_write_data"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                result = runner.execute(
                    ["/bin/sh", "-c", f"printf '%s\\n' '{marker}'; sleep 5"],
                    Path(directory) / "run", 2, budget_poll_interval=0.05,
                    linux_fail_fast=True)
                self.assertEqual(result["early_failure_marker"], marker)
                self.assertFalse(result.get("timeout", False))

    def test_probed_linux_ignores_raw_read_warning_but_stops_on_selected_x(self):
        for marker, expected in (("a_invalid_read_data", None),
                                 ("[CACHE_SELECTED_X]", "[CACHE_SELECTED_X]"),
                                 ("[CACHE_UNMATCHED_RESPONSE]", "[CACHE_UNMATCHED_RESPONSE]")):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                result = runner.execute(
                    ["/bin/sh", "-c", f"printf '%s\\n' '{marker}'; sleep 0.15",
                     "+CACHE_TAG_PROBE"], Path(directory) / "run", 2,
                    budget_poll_interval=0.05, linux_fail_fast=True)
                self.assertEqual(result.get("early_failure_marker"), expected)

    def test_linux_no_progress_guard_needs_progress_then_stall(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            result = runner.execute(
                ["/bin/sh", "-c", "printf '[SOC_PROGRESS] cycle=100 phase=LINUX_RUNNING\\n'; sleep 5"],
                run, 2, budget_poll_interval=0.05, no_progress_timeout=0.12)
            self.assertTrue(result["no_progress_timeout"])
            self.assertEqual(result["last_progress_cycle"], 100)
            self.assertFalse(result.get("timeout", False))

    def test_linux_first_progress_deadline_is_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            result = runner.execute(
                ["/bin/sh", "-c", "sleep 5"], Path(directory) / "run", 2,
                budget_poll_interval=0.05, first_progress_timeout=0.12)
            self.assertTrue(result["first_progress_timeout"])
            self.assertFalse(result.get("timeout", False))

    def test_initial_progress_prevents_first_progress_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            result = runner.execute(
                ["/bin/sh", "-c",
                 "printf '[SOC_PROGRESS] cycle=100 phase=LINUX_RUNNING\\n'; sleep 5"],
                Path(directory) / "run", 2, budget_poll_interval=0.05,
                first_progress_timeout=0.12, cycle_milestone=100)
            self.assertTrue(result["milestone_reached"])
            self.assertFalse(result.get("first_progress_timeout", False))

    def test_linux_cycle_milestone_is_diagnostic_not_boot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            result = runner.execute(
                ["/bin/sh", "-c",
                 "printf '[SOC_PROGRESS] cycle=100 phase=LINUX_RUNNING\\n'; sleep 5"],
                run, 2, budget_poll_interval=0.05, cycle_milestone=100)
            self.assertTrue(result["milestone_reached"])
            self.assertEqual(result["last_progress_cycle"], 100)
            self.assertEqual(result["cycle_milestone"], 100)
            self.assertFalse(result.get("timeout", False))

    def test_linux_uart_milestone_requires_completed_uart_line(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            result = runner.execute(
                ["/bin/sh", "-c",
                 "printf 'Linux version fake\\n[CANDIDATE_UART] Linux ver'; "
                 "sleep 0.1; printf 'sion 6.19\\n'; sleep 5"],
                run, 2, budget_poll_interval=0.02,
                uart_milestone="Linux version")
            self.assertEqual(result["uart_milestone_reached"], "Linux version")
            self.assertFalse(result.get("timeout", False))

    def test_linux_uart_monitor_rejects_non_uart_and_partial_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "console.log"
            monitor = runner.LinuxLogMonitor(log)
            log.write_bytes(b"Linux version fake\n[CANDIDATE_UART] Linux ver")
            monitor.update()
            self.assertNotIn("Linux version", monitor.uart_markers_seen)
            with log.open("ab") as stream:
                stream.write(b"sion 6.19\n")
            monitor.update()
            self.assertIn("Linux version", monitor.uart_markers_seen)

    def test_linux_failure_wins_over_uart_milestone(self):
        with tempfile.TemporaryDirectory() as directory:
            result = runner.execute(
                ["/bin/sh", "-c",
                 "printf 'Kernel panic\\n[CANDIDATE_UART] Linux version 6.19\\n'; sleep 5"],
                Path(directory) / "run", 2, budget_poll_interval=0.05,
                linux_fail_fast=True, uart_milestone="Linux version")
            self.assertEqual(result["early_failure_marker"], "Kernel panic")
            self.assertFalse(result.get("uart_milestone_reached", False))

    def test_linux_uart_milestone_cannot_be_boot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            def reached_milestone(_argv, run_dir, _timeout, *_args, **_kwargs):
                run_dir.mkdir()
                (run_dir / "console.log").write_text("[CANDIDATE_UART] Linux version 6.19\n")
                return {"returncode": -1, "uart_milestone_reached": "Linux version"}

            with (mock.patch.object(runner, "check_inputs"),
                  mock.patch.object(runner, "simulation_image", return_value={"simv": "hash"}),
                  mock.patch.object(runner, "execute", side_effect=reached_milestone)):
                result = {}
                runner.simulate(output, {"mode": "linux", "entry": 0x80000000},
                                result, 2, uart_milestone="Linux version")
            self.assertEqual(result["status"], "LINUX_UART_MILESTONE_REACHED")

    def test_linux_failure_wins_over_cycle_milestone(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            result = runner.execute(
                ["/bin/sh", "-c",
                 "printf 'Kernel panic\\n[SOC_PROGRESS] cycle=100 phase=LINUX_RUNNING\\n'; sleep 5"],
                run, 2, budget_poll_interval=0.05, linux_fail_fast=True,
                cycle_milestone=100)
            self.assertEqual(result["early_failure_marker"], "Kernel panic")
            self.assertFalse(result.get("milestone_reached", False))

    def test_milestone_result_cannot_be_reported_as_linux_boot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            def reached_milestone(_argv, run_dir, _timeout, *_args, **_kwargs):
                run_dir.mkdir()
                (run_dir / "console.log").write_text(
                    "[SOC_PROGRESS] cycle=100 phase=LINUX_RUNNING\n")
                return {"returncode": -1, "milestone_reached": True,
                        "last_progress_cycle": 100, "cycle_milestone": 100}

            with (mock.patch.object(runner, "check_inputs"),
                  mock.patch.object(runner, "simulation_image", return_value={"simv": "hash"}),
                  mock.patch.object(runner, "execute", side_effect=reached_milestone)):
                result = {}
                runner.simulate(output, {"mode": "linux", "entry": 0x80000000},
                                result, 2, cycle_milestone=100)
            self.assertEqual(result["status"], "LINUX_MILESTONE_REACHED")
            self.assertNotEqual(result["status"], "LINUX_BOOT_PASS")

    def test_run_only_rejects_changed_image_and_existing_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "inputs").mkdir()
            (output / "compile/simv.daidir").mkdir(parents=True)
            simv = output / "compile/simv"
            simv.write_bytes(b"launcher")
            (output / "compile/simv.daidir/rtl.so").write_bytes(b"design")
            manifest = {"inputs": {}, "entry": 0x80000000}
            (output / "inputs.json").write_text(json.dumps(manifest))
            summary = {
                "status": "COMPILED_NOT_RUN",
                "inputs_manifest_sha256": runner.sha((output / "inputs.json").read_bytes()),
                "compile": {"returncode": 0},
                "technology": {"passed": True},
                "simv_sha256": runner.sha(simv.read_bytes()),
            }
            (output / "summary.json").write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "mode differs"):
                runner.run_precompiled(output, 1, "linux")
            simv.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "executable changed"):
                runner.run_precompiled(output, 1)
            simv.write_bytes(b"launcher")
            (output / "sim").mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                runner.run_precompiled(output, 1)

    def test_compile_reuse_fingerprint_ignores_payload_but_not_rtl(self):
        def row(content):
            return {"sha256": runner.sha(content), "size_bytes": len(content)}

        manifest = {
            "compile_sources": ["package/rtl/core.sv", runner.TB],
            "include_dirs": ["package/rtl/include", "generated"],
            "inputs": {
                "package/rtl/core.sv": row(b"core"),
                runner.TB: row(b"tb"),
                runner.MODELS_TB: row(b"technology"),
                "package/rtl/include/core.svh": row(b"header"),
                "generated/board_cfg.svh": row(b"board"),
                "generated/memory.hex": row(b"old payload"),
                "package/linux/artifacts/Image": row(b"old Image"),
            },
        }
        changed = json.loads(json.dumps(manifest))
        changed["inputs"]["generated/memory.hex"] = row(b"new payload")
        changed["inputs"]["package/linux/artifacts/Image"] = row(b"new Image")
        self.assertEqual(runner.compiled_inputs(manifest), runner.compiled_inputs(changed))
        changed["inputs"]["package/rtl/include/core.svh"] = row(b"new header")
        self.assertNotEqual(runner.compiled_inputs(manifest), runner.compiled_inputs(changed))

    def test_linux_quiet_boot_flag_only_enters_opted_in_simulation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "compile").mkdir()
            (output / "compile/simv").write_bytes(b"simv")
            seen = []

            def execute(argv, cwd, timeout, *args, **kwargs):
                seen.append(argv)
                cwd.mkdir()
                (cwd / "console.log").write_text("SOC_LINUX_PASS mode=LINUX reason=UART_USERSPACE_MARKERS_AND_RTL_ACTIVITY\n")
                return {"returncode": 0}

            with mock.patch.object(runner, "check_inputs"), \
                    mock.patch.object(runner, "simulation_image", return_value={"simv": "same"}), \
                    mock.patch.object(runner, "execute", side_effect=execute):
                runner.simulate(output, {"mode": "linux", "entry": 0x80000000,
                                         "quiet_opensbi": True}, {}, 1)
            self.assertIn("+QUIET_OPENSBI", seen[0])

    def test_linux_assertion_rejects_pass_even_without_fail_fast(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "compile").mkdir()
            (output / "compile/simv").write_bytes(b"simv")

            def execute(_argv, cwd, _timeout, *_args, **_kwargs):
                cwd.mkdir()
                (cwd / "console.log").write_text(
                    "a_invalid_read_data: started at 10 failed at 10\n"
                    "SOC_LINUX_PASS mode=LINUX reason=UART_USERSPACE_MARKERS_AND_RTL_ACTIVITY\n")
                return {"returncode": 0}

            with mock.patch.object(runner, "check_inputs"), \
                    mock.patch.object(runner, "simulation_image", return_value={"simv": "same"}), \
                    mock.patch.object(runner, "execute", side_effect=execute):
                result = {}
                runner.simulate(output, {"mode": "linux", "entry": 0x80000000}, result, 1)
            self.assertEqual(result["status"], "LINUX_BOOT_FAILED")

    def test_probed_linux_requires_active_marker_and_selected_data(self):
        for active, selected_x, expected in ((False, False, "LINUX_BOOT_FAILED"),
                                             (True, False, "LINUX_BOOT_PASS"),
                                             (True, True, "LINUX_BOOT_FAILED")):
            with self.subTest(active=active, selected_x=selected_x), \
                    tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                (output / "compile").mkdir()
                (output / "compile/simv").write_bytes(b"simv")

                def execute(_argv, cwd, _timeout, *_args, **_kwargs):
                    cwd.mkdir()
                    log = "SOC_LINUX_PASS mode=LINUX reason=UART_USERSPACE_MARKERS_AND_RTL_ACTIVITY\n"
                    log += "a_invalid_read_data: started at 10 failed at 10\n"
                    if active:
                        log += runner.CACHE_PROBE_ACTIVE + "\n"
                    if selected_x:
                        log += "[CACHE_SELECTED_X] cycle=10\n"
                    (cwd / "console.log").write_text(log)
                    return {"returncode": 0}

                with mock.patch.object(runner, "check_inputs"), \
                        mock.patch.object(runner, "simulation_image", return_value={"simv": "same"}), \
                        mock.patch.object(runner, "execute", side_effect=execute):
                    result = {}
                    runner.simulate(output, {"mode": "linux", "entry": 0x80000000},
                                    result, 1, cache_tag_probe=True)
                self.assertEqual(result["status"], expected)


if __name__ == "__main__":
    unittest.main()
