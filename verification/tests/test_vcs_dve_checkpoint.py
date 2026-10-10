"""Host-only tests; never invoke VCS, Spike, DVE, or a processor image."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import run_vcs_dve_checkpoint as queue
import vcs_coverage_exec as adapter


class VcsDveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_build_changes_only_three_assignments(self):
        original = queue.read(queue.REFERENCE / "compile.command.json")["command"]
        command = queue.compile_command(self.root)
        changes = [(a, b) for a, b in zip(original, command) if a != b]
        self.assertEqual(len(original), len(command))
        self.assertEqual({a.split("=")[0] for a, b in changes}, {"code_coverage", "buildpath", "sim_dir"})
        for value in ("code_coverage=1", "verify_axi_delay=1", "verify_uvm_cvxif=1",
                      "fail_on_assert=0", "qbs=1", "akv=1", "akv_v2=1", "sim_l2_mb=2"):
            self.assertIn(value, command)
        extras = next(arg for arg in command if arg.startswith("verify_extra_sources="))
        self.assertEqual(len(extras.split("=", 1)[1].split()), 4)

    def config(self):
        image = self.root / "simv"
        image.write_text("fake image")
        cwd = self.root / "results/case/tests/test"
        cwd.mkdir(parents=True)
        return {"results": str(self.root / "results"), "simv": str(image),
                "image": {str(image): adapter.digest(image)}}, cwd

    def test_per_case_vdb_and_no_design_write(self):
        config, cwd = self.config()
        args = ["-l", "run.vcs.log", "+TESTCASE=test", "+PRELOAD=input.elf"]
        command = adapter.command(config, args, cwd)
        self.assertEqual(command[1:1 + len(args)], args)
        self.assertEqual(command[-6:], ["-cm", adapter.METRICS, "-cm_dir", str(cwd / "code.vdb"),
                                       "-cm_name", "test"])

    def test_adapter_rejects_override_existing_vdb_and_foreign_cwd(self):
        config, cwd = self.config()
        with self.assertRaises(ValueError):
            adapter.command(config, ["+TESTCASE=test", "-cm_dir", "foreign"], cwd)
        with self.assertRaises(ValueError):
            adapter.command(config, ["+TESTCASE=test"], self.root)
        (cwd / "code.vdb").mkdir()
        with self.assertRaises(ValueError):
            adapter.command(config, ["+TESTCASE=test"], cwd)

    def test_adapter_pins_actual_executable_not_only_wrapper(self):
        config, cwd = self.config()
        Path(config["simv"]).write_text("changed")
        with self.assertRaises(RuntimeError):
            adapter.command(config, ["+TESTCASE=test"], cwd)

    def test_replay_uses_existing_checker_and_explicit_oracle_isa(self):
        command = queue.replay_command(self.root, {"name": "seed509", "summary": "/frozen.json",
                                                   "testcase": "test", "spike": "/spike"})
        self.assertIn("replay-failed-rvv", command)
        self.assertIn("--include-passed", command)
        self.assertEqual(command[command.index("--spike-isa") + 1], "rv64gcv_zvfh_zvl1024b")
        self.assertNotIn("--code-coverage", command)

    def test_audit_requires_all_policies_and_matching_artifact(self):
        report = {"status": "PASS", "case_count": 1, "passed_cases": 1, "failed_cases": 0,
                  "errors": [], "cases": [{"name": "test", "status": "PASS", "errors": [],
                                            "artifact_dir": str(self.root)}],
                  "policy": {key: True for key in ("require_complete", "require_trace",
                                                   "require_vector", "require_full_match")}}
        queue.audit_ok(report, "test", self.root)
        report["policy"]["require_vector"] = False
        with self.assertRaises(RuntimeError):
            queue.audit_ok(report, "test", self.root)

    def test_design_vdb_must_stay_pure(self):
        queue.pure_design(self.root)
        test = self.root / "snps/coverage/db/testdata/default/line.data.xml"
        test.parent.mkdir(parents=True)
        test.write_text("data")
        with self.assertRaises(RuntimeError):
            queue.pure_design(self.root)

    def test_vdb_inventory_detects_new_files_and_content_changes(self):
        p = self.root / "line.data.xml"
        p.write_text("old")
        before = queue.inventory(self.root)
        p.write_text("new")
        self.assertNotEqual(before, queue.inventory(self.root))
        p.write_text("old")
        (self.root / "extra").write_text("unexpected")
        self.assertNotEqual(before, queue.inventory(self.root))

    def test_actual_vcs_command_only_allows_coverage_delta(self):
        def record(directory, extra):
            p = directory / "sim/simv.daidir/vcs_rebuild"
            p.parent.mkdir(parents=True)
            p.write_text(f"vcs -full64 -f {directory}/build/filelist {extra} 2>&1\n")
        reference, candidate = self.root / "ref", self.root / "candidate"
        record(reference, "")
        record(candidate, f"-cm {adapter.METRICS} -cm_dir {candidate}/sim/simv.vdb")
        self.assertEqual(queue.normalized_vcs(reference), queue.normalized_vcs(candidate, True))
        p = candidate / "sim/simv.daidir/vcs_rebuild"
        p.write_text(p.read_text().replace(adapter.METRICS, "line"))
        with self.assertRaises(RuntimeError):
            queue.normalized_vcs(candidate, True)

    def test_failed_replay_stops_before_audit_or_dve(self):
        queue.save(self.root / "status.json", {"status": "PREPARED"})
        (self.root / "inputs").mkdir()
        plan = {"cases": [{"name": "bad", "summary": "/summary", "testcase": "test", "spike": "/spike"}]}
        with patch.object(queue, "check_service"), patch.object(queue, "frozen", return_value=plan), \
                patch.object(queue, "quiescent_build"), patch.object(queue, "check_build", return_value={}), \
                patch.object(queue, "check"), patch.object(queue, "sources"), \
                patch.object(queue, "run", side_effect=RuntimeError("case failed")) as run:
            self.assertEqual(queue.execute(self.root, True, "build.service"), 1)
        self.assertEqual(run.call_count, 1)
        self.assertIn("replay-failed-rvv", run.call_args.args[0])
        self.assertEqual(queue.read(self.root / "status.json")["status"], "STOPPED")
        self.assertFalse((self.root / "collection.json").exists())


if __name__ == "__main__":
    unittest.main()
