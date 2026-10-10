import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "coverage" / "run_verilator_coverage.py"
MERGER = SCRIPT.with_name("merge_verilator_coverage.py")
AUDITOR = SCRIPT.with_name("audit_merged.py")
REVIEWER = SCRIPT.with_name("review_uncovered.py")
PROVENANCE = SCRIPT.with_name("build_provenance.py")
SPEC = importlib.util.spec_from_file_location("run_verilator_coverage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VerilatorCoverageTest(unittest.TestCase):
    def test_build_provenance_detects_source_and_include_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hardware = root / "hardware"
            include_dir = hardware / "deps" / "core" / "include"
            include_dir.mkdir(parents=True)
            (hardware / "src").mkdir()
            (hardware / "tb" / "verilator").mkdir(parents=True)
            (root / "config").mkdir()
            for path in (root / "Bender.yml", root / "Bender.lock",
                         root / "config" / "default.mk", root / "config" / "sram.mk",
                         hardware / "Makefile"):
                path.write_text("input\n")
            source = hardware / "src" / "core.sv"
            source.write_text("module core; endmodule\n")
            header = include_dir / "params.svh"
            header.write_text("`define VALUE 1\n")
            build = root / "build"
            build.mkdir()
            (build / ".build-signature").write_text("config-hash\n")
            filelist = build / "bender_script_default"
            filelist.write_text(f"+incdir+{include_dir}\n{source}\n")
            manifest = root / "manifest.json"
            command = [sys.executable, str(PROVENANCE), "--filelist", str(filelist),
                       "--repo-root", str(root), "--build-dir", str(build),
                       "--output", str(manifest)]
            captured = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            check = [sys.executable, str(PROVENANCE), "--output", str(manifest), "--check"]
            passed = subprocess.run(check, capture_output=True, text=True, check=False)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            header.write_text("`define VALUE 2\n")
            changed = subprocess.run(check, capture_output=True, text=True, check=False)
            self.assertEqual(changed.returncode, 1)
            self.assertIn(str(header), json.loads(changed.stdout)["changed"])

    def test_runner_freezes_simulator_and_elf_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "source-simv"
            simv.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "prefix = '+verilator+coverage+file+'\n"
                "out = next(arg[len(prefix):] for arg in sys.argv if arg.startswith(prefix))\n"
                "pathlib.Path(out).write_text(\"C 'point' 1\\n\")\n"
                "print('Core Test *** SUCCESS *** (tohost = 0)')\n"
            )
            simv.chmod(0o755)
            elf = root / "source.elf"
            elf.write_bytes(b"frozen-elf")
            reporter = root / "reporter"
            reporter.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[sys.argv.index('--write-info') + 1]).write_text("
                "'SF:/hardware/src/test.sv\\nDA:1,1\\nend_of_record\\n')\n"
            )
            reporter.chmod(0o755)
            output = root / "case"
            command = [sys.executable, str(SCRIPT), "--simv", str(simv),
                       "--elf", str(elf), "--output", str(output),
                       "--verilator-coverage", str(reporter)]
            process = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(Path(result["simv"]), output / "simv")
            self.assertEqual(Path(result["elf"]), output / "input.elf")
            self.assertEqual(result["simv_sha256"], hashlib.sha256(simv.read_bytes()).hexdigest())
            self.assertEqual(result["elf_sha256"], hashlib.sha256(elf.read_bytes()).hexdigest())
            simv.write_text("changed")
            elf.write_bytes(b"changed")
            self.assertEqual(hashlib.sha256((output / "simv").read_bytes()).hexdigest(),
                             result["simv_sha256"])
            self.assertEqual(hashlib.sha256((output / "input.elf").read_bytes()).hexdigest(),
                             result["elf_sha256"])

    def test_runner_forwards_tohost_address(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "simv"
            simv.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "assert '+COMMIT_TOHOST=0000000080002000' in sys.argv\n"
                "prefix = '+verilator+coverage+file+'\n"
                "out = next(arg[len(prefix):] for arg in sys.argv if arg.startswith(prefix))\n"
                "pathlib.Path(out).write_text(\"C 'point' 1\\n\")\n"
                "print('Core Test *** SUCCESS *** (tohost = 0)')\n"
            )
            simv.chmod(0o755)
            elf = root / "input.elf"
            elf.write_bytes(b"test-elf")
            reporter = root / "reporter"
            reporter.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[sys.argv.index('--write-info') + 1]).write_text("
                "'SF:/hardware/src/test.sv\\nDA:1,1\\nend_of_record\\n')\n"
            )
            reporter.chmod(0o755)
            output = root / "case"
            process = subprocess.run(
                [sys.executable, str(SCRIPT), "--simv", str(simv),
                 "--elf", str(elf), "--output", str(output),
                 "--verilator-coverage", str(reporter),
                 "--tohost-addr", "0x80002000"],
                capture_output=True, text=True, check=False)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["tohost_addr"], 0x80002000)
            self.assertEqual(result["status"], "PASS")

    def test_runner_rejects_nonzero_tohost_even_with_zero_process_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "simv"
            simv.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "prefix = '+verilator+coverage+file+'\n"
                "out = next(arg[len(prefix):] for arg in sys.argv if arg.startswith(prefix))\n"
                "pathlib.Path(out).write_text(\"C 'point' 1\\n\")\n"
                "print('Core Test *** SUCCESS *** (tohost = 1)')\n"
            )
            simv.chmod(0o755)
            elf = root / "input.elf"
            elf.write_bytes(b"test-elf")
            reporter = root / "reporter"
            reporter.write_text("#!/bin/sh\nexit 0\n")
            reporter.chmod(0o755)
            output = root / "case"
            process = subprocess.run(
                [sys.executable, str(SCRIPT), "--simv", str(simv),
                 "--elf", str(elf), "--output", str(output),
                 "--verilator-coverage", str(reporter)],
                capture_output=True, text=True, check=False)
            self.assertEqual(process.returncode, 1)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["sim_returncode"], 0)
            self.assertFalse(result["self_check_pass"])
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["sim_log_sha256"],
                             hashlib.sha256((output / "sim.log").read_bytes()).hexdigest())
            self.assertGreaterEqual(result["elapsed_s"], 0)
            self.assertIn("tohost = 1", result["sim_log_tail"][-1])

    def test_runner_preserves_timeout_log_and_excludes_partial_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "simv"
            simv.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys, time\n"
                "prefix = '+verilator+coverage+file+'\n"
                "out = next(arg[len(prefix):] for arg in sys.argv if arg.startswith(prefix))\n"
                "pathlib.Path(out).write_text(\"C 'partial' 1\\n\")\n"
                "print('unfinished simulation', flush=True)\n"
                "time.sleep(2)\n"
            )
            simv.chmod(0o755)
            elf = root / "input.elf"
            elf.write_bytes(b"test-elf")
            reporter = root / "reporter"
            reporter.write_text("#!/bin/sh\nexit 0\n")
            reporter.chmod(0o755)
            output = root / "case"
            process = subprocess.run(
                [sys.executable, str(SCRIPT), "--simv", str(simv),
                 "--elf", str(elf), "--output", str(output),
                 "--verilator-coverage", str(reporter), "--timeout", "1"],
                capture_output=True, text=True, check=False)
            self.assertEqual(process.returncode, 1)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("timeout", result["reason"])
            self.assertIn("unfinished simulation", result["sim_log_tail"])
            self.assertEqual(result["sim_log_sha256"],
                             hashlib.sha256((output / "sim.log").read_bytes()).hexdigest())
            self.assertEqual(result["coverage_sha256"],
                             hashlib.sha256((output / "coverage.dat").read_bytes()).hexdigest())
            self.assertGreaterEqual(result["elapsed_s"], 1)

    def test_merged_auditor_checks_frozen_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            merged = root / "merged"
            case.mkdir()
            merged.mkdir()

            def digest(path):
                return hashlib.sha256(path.read_bytes()).hexdigest()

            simv = case / "simv"
            elf = case / "case.elf"
            simv.write_bytes(b"instrumented-image")
            elf.write_bytes(b"real-data-elf")
            (case / "sim.log").write_text("Core Test *** SUCCESS *** (tohost = 0)\n")
            (case / "coverage.dat").write_text("C 'point' 1\n")
            (case / "coverage.info").write_text("SF:/hardware/src/test.sv\nDA:1,1\nend_of_record\n")
            result = case / "result.json"
            result.write_text(json.dumps({
                "status": "PASS", "sim_returncode": 0, "report_returncode": 0,
                "self_check_pass": True, "simv": str(simv), "elf": str(elf),
                "simv_sha256": digest(simv), "elf_sha256": digest(elf),
                "sim_log_sha256": digest(case / "sim.log"),
                "coverage_sha256": digest(case / "coverage.dat"),
                "coverage_info_sha256": digest(case / "coverage.info"),
            }))
            data = merged / "merged.dat"
            data.write_text(
                "# SystemC::Coverage-3\n"
                "C '\x01f\x02/hardware/src/test.sv\x01l\x021\x01t\x02line"
                "\x01h\x02tb.dut.core' 1\n"
                "C '\x01f\x02/hardware/src/test.sv\x01l\x022\x01t\x02expr"
                "\x01h\x02tb.dut.core' 0\n"
            )
            info = merged / "merged.info"
            info.write_text("SF:/hardware/src/test.sv\nDA:1,1\nDA:2,0\nend_of_record\n")
            uncovered = merged / "uncovered.jsonl"
            raw_scoped = MODULE.write_uncovered_raw(data, uncovered, "tb.dut",
                                                    ["/hardware/src/"])
            audit = merged / "audit.json"
            audit.write_text(json.dumps({
                "status": "PASS", "simv_sha256": digest(simv),
                "cases": [{"result": str(result), "result_sha256": digest(result),
                           "coverage": str(case / "coverage.dat"),
                           "coverage_sha256": digest(case / "coverage.dat")}],
                "merged_sha256": digest(data), "merged_info_sha256": digest(info),
                "uncovered_points": str(uncovered), "uncovered_sha256": digest(uncovered),
                "hierarchy_coverage": MODULE.summarize_raw(data, "tb.dut"),
                "scoped_raw_coverage": raw_scoped,
                "raw_coverage": MODULE.summarize_lcov(info),
                "include_paths": ["/hardware/src/"],
                "scoped_coverage": MODULE.summarize_lcov(info, ["/hardware/src/"]),
            }))
            command = [sys.executable, str(AUDITOR), "--audit", str(audit)]
            passed = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertEqual(json.loads(passed.stdout)["status"], "PASS")
            review = merged / "review.json"
            reviewed = subprocess.run(
                [sys.executable, str(REVIEWER), "--audit", str(audit),
                 "--output", str(review)], capture_output=True, text=True, check=False)
            self.assertEqual(reviewed.returncode, 0, reviewed.stdout + reviewed.stderr)
            findings = json.loads(review.read_text())
            self.assertEqual(findings["status"], "REVIEW_REQUIRED")
            self.assertEqual(findings["points_missed"], 1)
            self.assertEqual(findings["by_source"]["/hardware/src/test.sv"]["missed_lines"],
                             [["2", 1]])

            added = root / "added"
            added.mkdir()
            for name in ("simv", "case.elf", "sim.log", "coverage.dat", "coverage.info"):
                (added / name).write_bytes((case / name).read_bytes())
            added_result = json.loads(result.read_text())
            added_result["simv"] = str(added / "simv")
            added_result["elf"] = str(added / "case.elf")
            added_path = added / "result.json"
            added_path.write_text(json.dumps(added_result))
            reporter = root / "verilator_coverage"
            reporter.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "args = sys.argv\n"
                "if '--write' in args:\n"
                "    pathlib.Path(args[args.index('--write') + 1]).write_bytes("
                "pathlib.Path(%r).read_bytes())\n"
                "else:\n"
                "    pathlib.Path(args[args.index('--write-info') + 1]).write_bytes("
                "pathlib.Path(%r).read_bytes())\n" % (str(data), str(info)))
            reporter.chmod(0o755)
            extended = root / "extended"
            extend_command = [sys.executable, str(MERGER), "--extend-audit", str(audit),
                              "--case", str(added_path), "--output", str(extended),
                              "--verilator-coverage", str(reporter)]
            extension = subprocess.run(extend_command, capture_output=True, text=True,
                                       check=False)
            self.assertEqual(extension.returncode, 0, extension.stdout + extension.stderr)
            extended_record = json.loads((extended / "audit.json").read_text())
            self.assertEqual(len(extended_record["cases"]), 2)
            self.assertEqual(extended_record["include_paths"], ["/hardware/src/"])
            self.assertEqual(extended_record["hierarchy_coverage"]["hierarchy_prefix"],
                             "tb.dut")
            duplicate_command = [sys.executable, str(MERGER), "--extend-audit", str(audit),
                                 "--case", str(result), "--output", str(root / "duplicate"),
                                 "--verilator-coverage", str(reporter)]
            duplicate = subprocess.run(duplicate_command, capture_output=True, text=True,
                                       check=False)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("duplicate coverage case", duplicate.stderr)

            (added / "simv").write_bytes(b"different-instrumented-image")
            added_result["simv_sha256"] = digest(added / "simv")
            added_path.write_text(json.dumps(added_result))
            mixed_command = extend_command.copy()
            mixed_command[mixed_command.index("--output") + 1] = str(root / "mixed")
            mixed = subprocess.run(mixed_command, capture_output=True, text=True,
                                   check=False)
            self.assertNotEqual(mixed.returncode, 0)
            self.assertIn("different Verilator images", mixed.stderr)

            uncovered.write_text("changed\n")
            tampered = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("uncovered.jsonl", tampered.stdout)
            corrupt_command = extend_command.copy()
            corrupt_command[corrupt_command.index("--output") + 1] = str(root / "corrupt")
            corrupt = subprocess.run(corrupt_command, capture_output=True, text=True,
                                     check=False)
            self.assertNotEqual(corrupt.returncode, 0)
            self.assertIn("prior merge audit failed", corrupt.stderr)
            rejected = subprocess.run(
                [sys.executable, str(REVIEWER), "--audit", str(audit),
                 "--output", str(merged / "rejected.json")],
                capture_output=True, text=True, check=False)
            self.assertNotEqual(rejected.returncode, 0)

    def test_success_marker_matches_real_ara_testbench(self):
        self.assertIsNotNone(MODULE.SUCCESS.search(
            "Core Test *** SUCCESS *** (tohost = 0)"))
        self.assertIsNone(MODULE.SUCCESS.search(
            "Core Test *** FAILED *** (tohost = 1)"))
        self.assertIsNone(MODULE.SUCCESS.search(
            "Core Test *** SUCCESS *** (tohost = 1)"))
        self.assertIsNone(MODULE.SUCCESS.search(
            "Core Test **** SUCCESS **** (tohost = 0)"))

    def test_raw_hierarchy_scope_excludes_testbench(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "coverage.dat"
            data.write_text(
                "# SystemC::Coverage-3\n"
                "C '\x01t\x02line\x01h\x02TOP.tb.dut.core' 3\n"
                "C '\x01t\x02expr\x01h\x02tb.dut.core' 0\n"
                "C '\x01t\x02line\x01h\x02tb.monitor' 2\n"
            )
            self.assertEqual(
                MODULE.summarize_raw(data, "tb.dut"),
                {"hierarchy_prefix": "tb.dut", "points_total": 2,
                 "points_hit": 1,
                "by_type": {"line": {"total": 1, "hit": 1},
                             "expr": {"total": 1, "hit": 0}}},
            )

    def test_uncovered_listing_is_scoped_to_dut_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "coverage.dat"
            data.write_text(
                "# SystemC::Coverage-3\n"
                "C '\x01f\x02/hardware/src/core.sv\x01l\x0211\x01t\x02line"
                "\x01h\x02TOP.tb.dut.core\x01o\x02if' 0\n"
                "C '\x01f\x02/hardware/src/core.sv\x01l\x0212\x01t\x02expr"
                "\x01h\x02tb.dut.core' 3\n"
                "C '\x01f\x02/hardware/src/other.sv\x01l\x022\x01t\x02line"
                "\x01h\x02tb.monitor' 0\n"
            )
            missed = root / "uncovered.jsonl"
            result = MODULE.write_uncovered_raw(data, missed, "tb.dut",
                                                 ["/hardware/src/"])
            self.assertEqual(result["points_total"], 2)
            self.assertEqual(result["points_hit"], 1)
            self.assertEqual(result["by_source"]["/hardware/src/core.sv"],
                             {"total": 2, "hit": 1})
            points = [json.loads(line) for line in missed.read_text().splitlines()]
            self.assertEqual(points, [{"source": "/hardware/src/core.sv",
                                       "line": "11", "type": "line",
                                       "instance": "TOP.tb.dut.core",
                                       "label": "if", "point": None}])

    def test_merger_rejects_failed_or_mixed_image_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for number, status in ((1, "PASS"), (2, "FAIL")):
                case = root / f"case{number}"
                case.mkdir()
                simv = case / "simv"
                elf = case / "case.elf"
                simv.write_text(f"simv-{number}")
                elf.write_text(f"elf-{number}")
                (case / "coverage.dat").write_text("C 'x' 1\n")
                (case / "coverage.info").write_text("SF:case.sv\nDA:1,1\nend_of_record\n")
                (case / "sim.log").write_text("Core Test *** SUCCESS *** (tohost = 0)\n")
                digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
                result = case / "result.json"
                result.write_text(json.dumps({"status": status,
                                              "sim_returncode": 0,
                                              "report_returncode": 0,
                                              "self_check_pass": True,
                                              "simv": str(simv),
                                              "elf": str(elf),
                                              "simv_sha256": digest(simv),
                                              "elf_sha256": digest(elf),
                                              "sim_log_sha256": digest(case / "sim.log"),
                                              "coverage_sha256": digest(case / "coverage.dat"),
                                              "coverage_info_sha256": digest(case / "coverage.info")}))
                paths.append(result)

            command = [sys.executable, str(MERGER), "--case", str(paths[0]),
                       "--case", str(paths[1]), "--output", str(root / "merged"),
                       "--verilator-coverage", str(SCRIPT)]
            failed = subprocess.run(command, capture_output=True, text=True,
                                    check=False)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("case did not pass", failed.stderr)

            updated = json.loads(paths[1].read_text())
            updated["status"] = "PASS"
            paths[1].write_text(json.dumps(updated))
            mixed = subprocess.run(command, capture_output=True, text=True,
                                    check=False)
            self.assertNotEqual(mixed.returncode, 0)
            self.assertIn("different Verilator images", mixed.stderr)
            self.assertFalse((root / "merged").exists())

            (root / "case1" / "case.elf").write_text("changed")
            tampered = subprocess.run(command[:4] + command[6:],
                                      capture_output=True, text=True, check=False)
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("elf is missing or changed", tampered.stderr)

    def test_lcov_counts_unique_lines_and_branches(self):
        with tempfile.TemporaryDirectory() as directory:
            info = Path(directory) / "coverage.info"
            info.write_text(
                "SF:hardware/src/one.sv\n"
                "DA:10,3\nDA:11,0\n"
                "BRDA:10,0,0,2\nBRDA:10,0,1,0\n"
                "end_of_record\n"
                "SF:hardware/src/two.sv\n"
                "DA:10,1\nBRDA:10,0,0,-\n"
                "end_of_record\n"
            )
            self.assertEqual(
                MODULE.summarize_lcov(info),
                {"source_files": 2, "lines_total": 3, "lines_hit": 2,
                 "branches_total": 3, "branches_hit": 1},
            )
            self.assertEqual(
                MODULE.summarize_lcov(info, ["hardware/src/one.sv"]),
                {"source_files": 1, "lines_total": 2, "lines_hit": 1,
                 "branches_total": 2, "branches_hit": 1},
            )


if __name__ == "__main__":
    unittest.main()
