import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import run_passed_matrix  # noqa: E402
import run_directed_coverage  # noqa: E402


class PassedCoverageMatrixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.elf = self.source / "input.elf"
        self.elf.write_bytes(b"frozen ELF")
        coverage = self.source / "coverage.dat"
        coverage.write_bytes(b"coverage data")
        self.result = self.source / "result.json"
        self.record = {
            "status": "PASS",
            "self_check_pass": True,
            "elf": str(self.elf),
            "elf_sha256": hashlib.sha256(self.elf.read_bytes()).hexdigest(),
            "coverage_sha256": hashlib.sha256(coverage.read_bytes()).hexdigest(),
        }
        self.result.write_text(json.dumps(self.record), encoding="utf-8")
        self.case = {"name": "rvv", "source_result": "source/result.json",
                     "term_cycles": 20000, "timeout_s": 1200}

    def prepare(self):
        with patch.object(run_passed_matrix, "ROOT", self.root):
            return run_passed_matrix.prepare_case(self.case, self.inputs)

    def test_freezes_passing_input_and_provenance(self):
        frozen = self.prepare()
        self.assertEqual(Path(frozen["frozen_elf"]).read_bytes(), b"frozen ELF")
        self.assertEqual(frozen["source_result_sha256"],
                         hashlib.sha256(self.result.read_bytes()).hexdigest())

    def test_rejects_changed_input_or_coverage(self):
        self.elf.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "ELF hash mismatch"):
            self.prepare()
        self.elf.write_bytes(b"frozen ELF")
        (self.source / "coverage.dat").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "coverage hash mismatch"):
            self.prepare()

    def test_rejects_nonpassing_source(self):
        self.record["status"] = "TIMEOUT"
        self.result.write_text(json.dumps(self.record), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not a passing self-check"):
            self.prepare()

    def test_freezes_passing_uvm_input_and_rejects_log_drift(self):
        work = self.source / "work"
        work.mkdir()
        (work / "input.elf").write_bytes(b"real-data ELF")
        log = work / "run.vcs.log"
        log.write_text("Core Test *** SUCCESS *** (tohost = 0)\n")
        self.record = {
            "status": "PASS", "issues": [],
            "elf_sha256": hashlib.sha256((work / "input.elf").read_bytes()).hexdigest(),
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        }
        self.result.rename(self.source / "uvm_result.json")
        (self.source / "uvm_result.json").write_text(json.dumps(self.record))
        self.case.update(source_kind="uvm", source_result="source/uvm_result.json")
        frozen = self.prepare()
        self.assertEqual(Path(frozen["frozen_elf"]).read_bytes(), b"real-data ELF")
        self.assertEqual(frozen["source_kind"], "uvm")
        log.write_text("changed")
        with self.assertRaisesRegex(ValueError, "UVM log hash mismatch"):
            self.prepare()

    def test_replay_failure_preserves_first_error_and_other_results(self):
        cases = [{"name": "bad"}, {"name": "good"}]

        def fake_run(case, _simv, _reporter, output):
            target = output / case["name"]
            target.mkdir()
            result = target / "result.json"
            if case["name"] == "bad":
                result.write_text(json.dumps({"status": "FAIL", "reason": "self-check",
                                              "sim_log_tail": ["first mismatch"]}))
                raise RuntimeError("runner returned nonzero")
            result.write_text(json.dumps({"status": "PASS"}))
            return result

        with patch.object(run_passed_matrix, "run_case", side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, "bad: self-check"):
                run_passed_matrix.collect_cases(cases, self.root / "simv",
                                                self.root / "reporter", self.root, 2)
        summary = json.loads((self.root / "case_replay.json").read_text())
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual([case["status"] for case in summary["cases"]], ["FAIL", "PASS"])
        self.assertEqual(summary["first_error"]["sim_log_tail"], ["first mismatch"])

    def test_replay_success_records_both_cases(self):
        cases = [{"name": "a"}, {"name": "b"}]

        def fake_run(case, _simv, _reporter, output):
            target = output / case["name"]
            target.mkdir()
            result = target / "result.json"
            result.write_text(json.dumps({"status": "PASS"}))
            return result

        with patch.object(run_passed_matrix, "run_case", side_effect=fake_run):
            results = run_passed_matrix.collect_cases(cases, self.root / "simv",
                                                      self.root / "reporter", self.root, 2)
        self.assertEqual(len(results), 2)
        summary = json.loads((self.root / "case_replay.json").read_text())
        self.assertEqual(summary["status"], "PASS")
        self.assertIsNone(summary["first_error"])

    def test_run_case_forwards_tohost_only_when_present(self):
        case = {"name": "random", "frozen_elf": str(self.elf),
                "term_cycles": 100, "timeout_s": 10,
                "tohost_addr": 0x80002000}
        target = self.root / "random"
        target.mkdir()
        (target / "result.json").write_text(json.dumps({"status": "PASS"}))
        with patch.object(run_passed_matrix, "run") as mocked:
            run_passed_matrix.run_case(case, self.root / "simv",
                                       self.root / "reporter", self.root)
        self.assertIn("0x0000000080002000", mocked.call_args.args)
        self.assertIn("--tohost-addr", mocked.call_args.args)

    def test_reuse_requires_same_image_elf_and_terminal_contract(self):
        simv = self.root / "simv"
        simv.write_bytes(b"image")
        self.record["tohost_addr"] = 0x80002000
        self.result.write_text(json.dumps(self.record))
        audit = self.root / "audit.json"
        previous = {"simv_sha256": run_passed_matrix.digest(simv),
                    "cases": [{"result": str(self.result)}]}
        audit.write_text(json.dumps(previous))
        case = {"name": "random", "frozen_elf": str(self.elf),
                "tohost_addr": 0x80002000}
        with patch.object(run_passed_matrix, "audit_coverage", return_value={"status": "PASS"}):
            selected = run_passed_matrix.reuse_passed_cases([case], audit, simv)
            self.assertEqual(selected[0]["reuse_result"], str(self.result))
            with patch.object(run_passed_matrix, "run") as invoke:
                result = run_passed_matrix.run_case(selected[0], simv, self.root, self.root)
                self.assertEqual(result, self.result)
                invoke.assert_not_called()
            for mismatch in ({**case, "tohost_addr": None},
                             {**case, "tohost_addr": 0x80004000}):
                selected = run_passed_matrix.reuse_passed_cases([mismatch], audit, simv)
                self.assertNotIn("reuse_result", selected[0])
            self.elf.write_bytes(b"different ELF")
            selected = run_passed_matrix.reuse_passed_cases([case], audit, simv)
            self.assertNotIn("reuse_result", selected[0])
            simv.write_bytes(b"different image")
            with self.assertRaisesRegex(ValueError, "different simulator image"):
                run_passed_matrix.reuse_passed_cases([case], audit, simv)

    def test_reuse_rejects_unaudited_artifacts(self):
        with patch.object(run_passed_matrix, "audit_coverage", return_value={
                "status": "FAIL", "issues": ["coverage hash changed"]}):
            with self.assertRaisesRegex(ValueError, "coverage hash changed"):
                run_passed_matrix.reuse_passed_cases([], self.root / "audit.json",
                                                     self.root / "simv")

    def test_replay_records_reused_result_path(self):
        case = {"name": "cached", "reuse_result": str(self.result)}
        with patch.object(run_passed_matrix, "run") as invoke:
            results = run_passed_matrix.collect_cases([case], self.root, self.root,
                                                      self.root, 1)
        self.assertEqual(results, [self.result])
        invoke.assert_not_called()
        record = json.loads((self.root / "case_replay.json").read_text())["cases"][0]
        self.assertEqual(record["result"], str(self.result))
        self.assertTrue(record["reused"])

    def test_elf_fit_uses_selected_image_capacity(self):
        cases = [{"frozen_elf": str(self.elf)}]
        command = run_passed_matrix.elf_fit_command(cases, 2 * 1024 * 1024,
                                                     self.root)
        self.assertEqual(command[command.index("--ram-bytes") + 1], "2097152")
        self.assertEqual(command[command.index("--elf") + 1], str(self.elf))
        self.assertEqual(command[-1], str(self.root / "elf_fit.json"))


class DirectedCoverageSelectionTests(unittest.TestCase):
    def test_selects_only_named_audited_cases_in_source_order(self):
        cases = [{"name": "load"}, {"name": "store"}, {"name": "restart"}]
        self.assertEqual(run_directed_coverage.select_cases(cases, []), cases)
        self.assertEqual(run_directed_coverage.select_cases(cases, ["store", "load"]),
                         cases[:2])

    def test_rejects_duplicate_or_unknown_names(self):
        cases = [{"name": "load"}, {"name": "store"}]
        for names in (["load", "load"], ["missing"]):
            with self.subTest(names=names):
                with self.assertRaisesRegex(ValueError, "case names must be unique"):
                    run_directed_coverage.select_cases(cases, names)


if __name__ == "__main__":
    unittest.main()
