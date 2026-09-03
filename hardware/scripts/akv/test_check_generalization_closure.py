#!/usr/bin/env python3

import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check-generalization-closure.py")
SPEC = importlib.util.spec_from_file_location("check_generalization_closure", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CheckGeneralizationClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest_path = Path(__file__).with_name("generalization-closure-manifest.json")
        cls.manifest = json.loads(cls.manifest_path.read_text(encoding="utf-8"))
        cls.host_path = MODULE.path(cls.manifest["host_census"])
        cls.host = json.loads(cls.host_path.read_text(encoding="utf-8"))

    def require_file(self, artifact: Path, label: str) -> Path:
        if not artifact.is_file():
            self.skipTest(f"{label} is not installed in this worktree: {artifact}")
        return artifact

    def require_host_case_artifacts(self):
        dynamic = MODULE.csv_rows(self.host_path.with_name("dynamic_counts.csv"))
        missing = [
            MODULE.path(row["artifact"])
            for row in dynamic
            if not MODULE.path(row["artifact"]).is_file()
        ]
        if missing:
            self.skipTest(
                f"host census case artifacts are not installed in this worktree: {missing[0]}"
            )

    def test_current_census_has_strict_provenance(self):
        self.require_host_case_artifacts()
        artifacts = MODULE.validate_host_census(self.host, self.manifest)
        self.assertEqual({path.name for path in artifacts}, {
            "dynamic_counts.csv", "support_matrix.csv", "provenance.json"
        })

    def test_wrong_model_shape_cannot_pass_by_preserving_totals(self):
        host = copy.deepcopy(self.host)
        host["models"][2]["gqa_rows"] = "4"
        with self.assertRaisesRegex(ValueError, "shape/disposition differs"):
            MODULE.validate_host_census(host, self.manifest)

    def test_wrong_model_identity_cannot_pass_by_preserving_count(self):
        host = copy.deepcopy(self.host)
        host["models"][0]["id"] = "replacement_model"
        with self.assertRaisesRegex(ValueError, "frozen support contract"):
            MODULE.validate_host_census(host, self.manifest)

    def test_simulator_freshness_detects_newer_input(self):
        original_root = MODULE.ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                MODULE.ROOT = Path(directory)
                simv = MODULE.ROOT / "simv"
                source = MODULE.ROOT / "source.sv"
                filelist = MODULE.ROOT / "files.f"
                simv.write_text("simulator\n", encoding="utf-8")
                source.write_text("module source; endmodule\n", encoding="utf-8")
                filelist.write_text(str(source) + "\n", encoding="utf-8")
                os.utime(simv, ns=(1_000_000_000, 1_000_000_000))
                os.utime(filelist, ns=(1_000_000_000, 1_000_000_000))
                os.utime(source, ns=(2_000_000_000, 2_000_000_000))
                _, _, stale = MODULE.inspect_simulator({
                    "simv": "simv", "filelist": "files.f", "metadata_sources": []
                })
                self.assertEqual(stale, [source])
        finally:
            MODULE.ROOT = original_root

    def test_simulator_contract_rejects_missing_required_define(self):
        original_root = MODULE.ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                MODULE.ROOT = Path(directory)
                simv = MODULE.ROOT / "simv"
                source = MODULE.ROOT / "source.sv"
                filelist = MODULE.ROOT / "files.f"
                simv.write_text("simulator\n", encoding="utf-8")
                source.write_text("module source; endmodule\n", encoding="utf-8")
                filelist.write_text("+define+ARA_AKV_ENABLE=1\n" + str(source) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "ARA_QBS_ENABLE=1"):
                    MODULE.inspect_simulator({
                        "simv": "simv",
                        "filelist": "files.f",
                        "metadata_sources": [],
                        "required_defines": ["ARA_AKV_ENABLE=1", "ARA_QBS_ENABLE=1"],
                    })
        finally:
            MODULE.ROOT = original_root

    def test_current_run_requires_matching_simulator_hash(self):
        original_root = MODULE.ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                MODULE.ROOT = Path(directory)
                simv = MODULE.ROOT / "simv"
                capture = MODULE.ROOT / "capture"
                run = MODULE.ROOT / "run"
                capture.mkdir()
                run.mkdir()
                simv.write_text("current simulator\n", encoding="utf-8")
                log = run / "ara.log"
                log.write_text("log\n", encoding="utf-8")
                (run / "complete").touch()
                (run / "run.conf").write_text(
                    f"simv={simv}\n"
                    f"simv_sha256={MODULE.sha256(simv)}\n"
                    f"capture_root={capture}\n",
                    encoding="utf-8",
                )
                MODULE.validate_current_run(
                    log, simv, {"capture_root": str(capture)}
                )
                (run / "run.conf").write_text(
                    f"simv={simv}\n"
                    f"simv_sha256={'0' * 64}\n"
                    f"capture_root={capture}\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "hash differs"):
                    MODULE.validate_current_run(
                        log, simv, {"capture_root": str(capture)}
                    )
        finally:
            MODULE.ROOT = original_root

    def test_directed_vcs_provenance_rejects_newer_source(self):
        original_root = MODULE.ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                MODULE.ROOT = Path(directory)
                build = MODULE.ROOT / "build"
                build.mkdir()
                source = MODULE.ROOT / "source.sv"
                source.write_text("module source; endmodule\n", encoding="utf-8")
                compile_log = build / "compile.log"
                compile_log.write_text(
                    f"Command: vcs {source} -top source -o simv\n"
                    " Chronologic VCS (TM)\n",
                    encoding="utf-8",
                )
                simv = build / "simv"
                simv.write_text("simulator\n", encoding="utf-8")
                timestamp = build / "simv.daidir/.vcs.timestamp"
                timestamp.parent.mkdir()
                timestamp.write_text(f"1 {source}\n", encoding="utf-8")
                run_log = build / "run.log"
                run_log.write_text("PASS\n", encoding="utf-8")
                os.utime(simv, ns=(1_000_000_000, 1_000_000_000))
                os.utime(source, ns=(2_000_000_000, 2_000_000_000))
                os.utime(run_log, ns=(3_000_000_000, 3_000_000_000))
                with self.assertRaisesRegex(ValueError, "predates compile inputs"):
                    MODULE.validate_directed_vcs_log(run_log, "akv_directed")
        finally:
            MODULE.ROOT = original_root

    def test_directed_vcs_provenance_accepts_symlinked_dependency(self):
        original_root = MODULE.ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                MODULE.ROOT = base / "worktree"
                build = MODULE.ROOT / "build"
                build.mkdir(parents=True)
                dependency = base / "shared-dependency"
                dependency.mkdir()
                source = dependency / "source.sv"
                source.write_text("module source; endmodule\n", encoding="utf-8")
                linked_dependency = MODULE.ROOT / "deps"
                linked_dependency.symlink_to(dependency, target_is_directory=True)

                compile_log = build / "compile.log"
                compile_log.write_text(
                    f"Command: vcs {linked_dependency / 'source.sv'} "
                    "-top source -o simv\n Chronologic VCS (TM)\n",
                    encoding="utf-8",
                )
                simv = build / "simv"
                simv.write_text("simulator\n", encoding="utf-8")
                timestamp = build / "simv.daidir/.vcs.timestamp"
                timestamp.parent.mkdir()
                timestamp.write_text(
                    f"1 {linked_dependency / 'source.sv'}\n", encoding="utf-8"
                )
                os.utime(source, ns=(1_000_000_000, 1_000_000_000))

                observed_simv, observed_timestamp, _ = (
                    MODULE.validate_vcs_compile_image(compile_log)
                )
                self.assertEqual(observed_simv, simv)
                self.assertEqual(observed_timestamp, timestamp)
        finally:
            MODULE.ROOT = original_root

    def test_frozen_qemu_covers_exact_seven_model_set(self):
        spec = self.manifest["frozen_full_model_qemu"]
        summary_path = self.require_file(
            MODULE.path(spec["summary"]), "frozen full-model QEMU summary"
        )
        self.require_file(MODULE.path(spec["complete"]), "frozen full-model QEMU marker")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(MODULE.validate_frozen_qemu(summary, self.manifest), (908688, 82, 258))

    def test_frozen_qemu_rejects_hidden_emulation(self):
        spec = self.manifest["frozen_full_model_qemu"]
        summary_path = self.require_file(
            MODULE.path(spec["summary"]), "frozen full-model QEMU summary"
        )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["models"][0]["qemu_qbs_emulated_commands"] = 1
        with self.assertRaisesRegex(ValueError, "native QBS model work"):
            MODULE.validate_frozen_qemu(summary, self.manifest)

    def test_current_physical_gate_distinguishes_preflight_from_results(self):
        checks = {check["name"]: check for check in MODULE.audit(self.manifest)}
        if checks["synthesis_preflight"]["status"] == "PENDING":
            self.skipTest(checks["synthesis_preflight"]["detail"])
        self.assertEqual(checks["synthesis_preflight"]["status"], "PASS")
        self.assertEqual(checks["physical_closure"]["status"], "PENDING")
        self.assertIn("synthesis_summary.json", checks["physical_closure"]["detail"])


if __name__ == "__main__":
    unittest.main()
