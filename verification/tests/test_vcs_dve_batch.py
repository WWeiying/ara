"""Host-only tests of VCS batching, oracles, inheritance and coverage gating."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import run_vcs_dve_batch as batch


class BatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def database(self, test="test"):
        vdb = self.root / "code.vdb"
        directory = vdb / "snps/coverage/db/testdata" / test
        directory.mkdir(parents=True)
        command = f"/image -cm {batch.base.METRICS} -cm_dir {vdb} -cm_name {test}"
        with gzip.open(directory / "siminfo.xml", "wt") as stream:
            stream.write(f'<test><srctest starttime="1" finishtime="2" cmdline="{escape(command)}"/></test>')
        for name in batch.METRIC_FILES:
            with gzip.open(directory / name, "wt") as stream:
                stream.write('<covdata><instance_data name="ara_tb" value="01"/></covdata>')
        return vdb, directory

    def test_complete_gzipped_vdb_valid(self):
        vdb, _ = self.database()
        self.assertEqual(len(batch.valid_vdb(vdb, "test", "/image")), 6)

    def test_truncated_gzip_rejected(self):
        vdb, directory = self.database()
        p = directory / "line.verilog.data.xml"
        p.write_bytes(p.read_bytes()[:-8])
        with self.assertRaises((EOFError, OSError)):
            batch.valid_vdb(vdb, "test", "/image")

    def test_missing_metric_rejected(self):
        vdb, directory = self.database()
        (directory / "tgl.verilog.data.xml").unlink()
        with self.assertRaises(ValueError):
            batch.valid_vdb(vdb, "test", "/image")

    def test_wrong_image_rejected(self):
        vdb, _ = self.database()
        with self.assertRaises(ValueError):
            batch.valid_vdb(vdb, "test", "/other-image")

    def test_adapter_preserves_directed_testcase_hyphens(self):
        work = self.root / "results/case/tests/test/work"
        work.mkdir(parents=True)
        config = {"results": str(self.root / "results"), "image": {}, "simv": "/image"}
        args = ["+TESTCASE=rv64uv-ara-vssseg", "+PRELOAD=frozen.elf"]
        command = batch.adapter_command(config, args, work)
        self.assertEqual(command[1:3], args)
        self.assertEqual(command[-1], "rv64uv_ara_vssseg")
        self.assertEqual(command[-3], str(work / "code.vdb"))

    def test_commands_select_distinct_oracles(self):
        directed = {"name": "d", "kind": "directed"}
        command, audit = batch.commands(self.root, directed, {})
        self.assertIn("--directed", command)
        self.assertIn("--require-trace", audit)
        self.assertNotIn("--require-vector", audit)
        random = {"name": "r", "kind": "random", "replay_summary": "/frozen.json", "source_name": "test",
                  "spike": "/spike", "timeout_s": 300, "spike_timeout_s": 60, "watchdog_cycles": 100000}
        command, audit = batch.commands(self.root, random, {"wrapper": "/wrapper"})
        self.assertIn("replay-failed-rvv", command)
        self.assertIn("rv64gcv_zvfh_zvl1024b", command)
        self.assertIn("--require-vector", audit)
        self.assertIn("--require-full-match", audit)

    def test_directed_uses_frozen_binary_and_never_builds(self):
        case = {"name": "directed", "kind": "directed", "source_files": {}, "frozen_elf": "/frozen.elf",
                "timeout_s": 300, "directed_test": {"name": "rvv:vssseg", "kind": "rvv",
                  "build_target": "unused", "binary": "/apps/must-not-use.elf", "testcase": "rv64uv-ara-vssseg",
                  "timeout_s": 300}}
        with patch.object(batch, "frozen", return_value={"cases": [case], "wrapper": "/wrapper"}), \
                patch.object(batch, "RegressionRunner") as runner:
            runner.return_value.run.return_value = [Mock(status="PASS")]
            self.assertEqual(batch.directed(self.root, "directed"), 0)
        options, tests, _ = runner.call_args.args
        self.assertTrue(options.skip_build)
        self.assertFalse(options.code_coverage)
        self.assertTrue(options.commit_trace)
        self.assertEqual(str(tests[0].binary), "/frozen.elf")
        self.assertEqual(tests[0].testcase, "rv64uv-ara-vssseg")

    def test_directed_audit_does_not_require_vector_but_random_does(self):
        report = {"status": "PASS", "case_count": 1, "passed_cases": 1, "failed_cases": 0,
                  "cases": [{"status": "PASS", "name": "rvv:test", "artifact_dir": str(self.root)}],
                  "policy": {"require_complete": True, "require_trace": True}}
        case = {"kind": "directed", "source_name": "rvv:test"}
        batch.audit_ok(report, case, self.root)
        with self.assertRaises(RuntimeError):
            batch.audit_ok(report, dict(case, kind="random"), self.root)

    def test_selection_keeps_233_and_15_exclusions(self):
        rows = [{"name": str(i), "kind": "random" if i < 186 else "directed"} for i in range(248)]
        batch.save(self.root / "plan.json", {"cases": rows})
        batch.save(self.root / "checkpoint.json", {"status": "STOPPED", "total": 248,
                    "cases": {str(i): {"status": "PASS" if i < 233 else "FAIL"} for i in range(248)}})
        selected, record = batch.selection(self.root)
        self.assertEqual(len(selected), 233)
        self.assertEqual(len(record["excluded"]), 15)
        self.assertFalse(record["complete_original_batch"])

    def test_eight_workers_are_really_concurrent(self):
        children, active_sizes = [], []
        def spawn(*args, **kwargs):
            child = Mock(pid=100 + len(children))
            child.poll.side_effect = lambda: None if len(children) < 8 else 0
            children.append(child)
            active_sizes.append(len(children))
            return child
        with patch.object(batch.subprocess, "Popen", side_effect=spawn), \
                patch.object(batch.time, "sleep"), patch.object(batch, "stop_groups") as stop:
            batch.schedule(self.root, [str(i) for i in range(8)], 8)
        self.assertEqual(max(active_sizes), 8)
        self.assertEqual(len(children), 8)
        stop.assert_not_called()

    def test_failure_observed_before_any_more_dispatch(self):
        child = Mock(pid=123)
        child.poll.return_value = 1
        with patch.object(batch.subprocess, "Popen", return_value=child) as spawn, \
                patch.object(batch, "stop_groups", return_value={"status": "REAPED"}) as stop:
            with self.assertRaises(RuntimeError):
                batch.schedule(self.root, [str(i) for i in range(12)], 8)
        self.assertEqual(spawn.call_count, 1)
        stop.assert_called_once()

    def test_complete_outcome_never_rerun(self):
        batch.save(self.root / "outcomes/old.json", {"status": "PASS"})
        with patch.object(batch, "frozen") as frozen:
            self.assertEqual(batch.worker(self.root, "old"), 1)
        frozen.assert_not_called()

    def test_per_worker_skips_shared_rtl_but_checks_image_and_checker(self):
        config = self.root / "inputs/coverage-wrapper.json"
        conf = self.root / "inputs/simulator.conf"
        plan = {"files": {"/rtl.sv": "rtl", "/checker.py": "checker", str(config): "config", str(conf): "conf"},
                "image": {"/simv": "image"}, "wrapper_image": {"/wrapper": "adapter"},
                "oracles": {"/spike": "oracle"}, "cases": []}
        batch.save(self.root / "plan.json", plan)
        batch.save(self.root / "plan.sha256.json", {})
        with patch.object(batch, "check") as check:
            batch.frozen(self.root)
        runtime = check.call_args_list[-1].args[0]
        self.assertNotIn("/rtl.sv", runtime)
        self.assertEqual(runtime["/checker.py"], "checker")
        self.assertEqual(runtime["/simv"], "image")
        self.assertEqual(runtime["/spike"], "oracle")
        with patch.object(batch, "check") as check:
            batch.frozen(self.root, all_cases=True)
        self.assertIn("/rtl.sv", check.call_args_list[-1].args[0])

    def test_dve_timeout_and_two_collections(self):
        cases = [{"name": "pass"}, {"name": "fail"}, {"name": "timeout"}]
        for case in cases:
            name = case["name"]
            batch.save(self.root / "outcomes" / (name + ".json"),
                       {"name": name, "status": "PASS" if name == "pass" else "FAIL", "files": {},
                        "vdb_valid": name != "timeout", "passed_only": name == "pass",
                        "vdb": "/" + name + ".vdb", "coverage_test": "test", "vdb_files": {}})
        plan = {"cases": cases, "design_vdb": "/design.vdb", "design_files": {},
                "source_selection": {}, "image": {}}
        def invoke(command, log, timeout, env=None):
            self.assertEqual(timeout, 720)
            self.assertEqual(env, {"DVE_COVERAGE_TIMEOUT": "600"})
            output = Path(command[2])
            output.mkdir()
            (output / "selected_tests.txt").write_text("\n".join(str(Path(p).with_suffix("") / "test")
                                                                   for p in command[4:]) + "\n")
            (output / "summary.csv").write_text("Name,Line\nara,5\n")
            return 0
        with patch.object(batch.base, "pure_design"), patch.object(batch.base, "inventory", return_value={}), \
                patch.object(batch, "invoke", side_effect=invoke):
            batch.summarize(self.root, plan)
        strict = batch.read(self.root / "passed-only/collection.json")
        exploration = batch.read(self.root / "exploration/collection.json")
        self.assertEqual([c["name"] for c in strict["samples"]], ["pass"])
        self.assertEqual([c["name"] for c in exploration["samples"]], ["pass", "fail"])
        self.assertEqual(exploration["excluded_incomplete_vdb"], ["timeout"])


if __name__ == "__main__":
    unittest.main()
