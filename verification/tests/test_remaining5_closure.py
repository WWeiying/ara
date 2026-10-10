from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_remaining5_closure as runner


class RemainingFiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def manifest(self):
        evidence = self.root / "repair.json"
        evidence.write_text('{"scope":"fixture"}')
        rows = []
        for seed in (1409, 1410, 1412):
            elf = self.root / f"fixed{seed}.elf"
            elf.write_bytes(f"fixed-{seed}".encode())
            rows.append({"seed": seed, "original_elf_sha256": "original",
                         "elf": elf.name, "elf_sha256": runner.sha256(elf),
                         "reason": "bounded OOB correction", "evidence": [
                             {"path": evidence.name, "sha256": runner.sha256(evidence)}]})
        path = self.root / "replacements.json"
        runner.save(path, {"schema_version": 1, "replacements": rows})
        return path, rows

    def test_replacements_require_three_distinct_explicit_mappings(self):
        path, rows = self.manifest()
        with patch.object(runner, "ROOT", self.root):
            replacements, files = runner.replacement_inputs(path)
            self.assertEqual(set(replacements), {1409, 1410, 1412})
            self.assertIn(path, files)
            self.assertTrue(all(Path(x["elf"]).is_absolute() for x in replacements.values()))
            runner.save(path, {"schema_version": 1, "replacements": rows[:2]})
            with self.assertRaisesRegex(RuntimeError, "exactly"):
                runner.replacement_inputs(path)

    def test_replacement_cannot_be_old_oob_elf(self):
        path, rows = self.manifest()
        rows[0]["original_elf_sha256"] = rows[0]["elf_sha256"]
        runner.save(path, {"schema_version": 1, "replacements": rows})
        with patch.object(runner, "ROOT", self.root), self.assertRaisesRegex(RuntimeError, "old OOB"):
            runner.replacement_inputs(path)

    def test_changed_replacement_or_missing_evidence_rejected(self):
        path, rows = self.manifest()
        with patch.object(runner, "ROOT", self.root):
            (self.root / rows[0]["elf"]).write_bytes(b"drift")
            with self.assertRaisesRegex(RuntimeError, "hash differs"):
                runner.replacement_inputs(path)
        path, rows = self.manifest()
        rows[0]["evidence"] = []
        runner.save(path, {"schema_version": 1, "replacements": rows})
        with patch.object(runner, "ROOT", self.root), self.assertRaisesRegex(RuntimeError, "evidence"):
            runner.replacement_inputs(path)

    def record(self):
        return {"image_root": str(runner.IMAGE), "spike": "spike", "workers": 5,
                "jobs": {f"seed{s}": {"kind": "replay", "seed": s, "summary": "frozen.json",
                         "case": f"case{s}", "fault_vstart_probe": s in (1401, 1402),
                         "replacement": s in runner.REPLACEMENTS, "elf_sha256": str(s)}
                         for s in runner.SEEDS}}

    def test_strict_flags_probe_only_originals_no_build(self):
        record = self.record()
        for name, spec in record["jobs"].items():
            command, audit = runner.commands(self.root, name, record)
            self.assertIn("replay-failed-rvv", command)
            self.assertEqual("--fault-vstart-probe" in command, not spec["replacement"])
            self.assertEqual(command[command.index("--simv") + 1], str(runner.IMAGE / "sim/simv"))
            self.assertTrue({"--require-trace", "--require-vector", "--require-full-match"} <= set(audit))
            self.assertNotIn("--include-passed", command)

    def probe(self):
        diagnostic = self.root / "probe.json"
        response = {"current_insn": "2e238a07", "cause": "4", "tval": "80009c7f",
                    "exception_vstart": "0", "csr_vstart_d": "0"}
        runner.save(diagnostic, {"response": response})
        resp = " ".join(f"{k}={v}" for k, v in response.items())
        log = (f"[ARA_FAULT_VSTART] phase=RESP inst=dut cycle=10 event=1 fire=1 "
               f"backend_valid=1 backend_exception=1 {resp}\n"
               "[ARA_FAULT_VSTART] phase=NEXT inst=dut cycle=11 event=1 rst_n=1 actual_q=0\n")
        (self.root / "run.vcs.log").write_text(log)
        return diagnostic, log

    def test_probe_is_capture_only_not_case_pass(self):
        diagnostic, _ = self.probe()
        result = runner.check_probe(self.root, diagnostic)
        self.assertEqual(result["status"], "CAPTURE_CONFIRMED")
        self.assertTrue(result["not_case_pass"])

    def test_probe_missing_delayed_wrong_q_or_reset_rejected(self):
        diagnostic, log = self.probe()
        for changed in (log.splitlines()[0], log.replace("cycle=11", "cycle=12"),
                        log.replace("actual_q=0", "actual_q=2"), log.replace("rst_n=1", "rst_n=0"), ""):
            with self.subTest(log=changed):
                (self.root / "run.vcs.log").write_text(changed)
                with self.assertRaises(RuntimeError):
                    runner.check_probe(self.root, diagnostic)

    def test_scheduler_failure_stops_and_never_relabels_history(self):
        runner.save(self.root / "checkpoint.json", {"status": "PREPARED", "cases": {
            "seed1409": {"status": "PENDING", "original_status": "INFRASTRUCTURE_ERROR"}}})
        with patch.object(runner, "check_service"), patch.object(runner, "check_frozen", return_value=self.record()), \
             patch.object(runner.prior, "run", side_effect=RuntimeError("first failed")) as launch:
            with self.assertRaisesRegex(RuntimeError, "first failed"):
                runner.execute(self.root)
            self.assertEqual(launch.call_count, 1)
        state = runner.read(self.root / "checkpoint.json")
        self.assertEqual(state["status"], "STOPPED")
        self.assertEqual(state["cases"]["seed1409"]["original_status"], "INFRASTRUCTURE_ERROR")

    def test_all_five_success_is_explicitly_two_original_three_replacement(self):
        record = self.record()
        runner.save(self.root / "checkpoint.json", {"status": "PREPARED", "cases": {
            name: {"status": "PENDING"} for name in record["jobs"]}})
        runner.save(self.root / "scheduler/status.json", {"status": "PASS", "results": [
            {"name": name, "status": "PASS"} for name in record["jobs"]]})
        for name, spec in record["jobs"].items():
            runner.save(self.root / "verdicts" / f"{name}.json", {
                "status": "PASS", "elf_sha256": spec["elf_sha256"], "replacement": spec["replacement"]})
        with patch.object(runner, "check_service"), patch.object(runner, "check_frozen", return_value=record), \
             patch.object(runner.prior, "run"):
            runner.execute(self.root)
        state = runner.read(self.root / "checkpoint.json")
        self.assertEqual(state["status"], "SELECTED_PASS")
        self.assertEqual((state["original_elf_passes"], state["replacement_passes"],
                          state["historical_failures_relabelled"]), (2, 3, 0))

    def test_frozen_manifest_drift_blocks_before_job(self):
        runner.save(self.root / "frozen.json", {})
        runner.save(self.root / "checkpoint.json", {"frozen_sha256": "different"})
        with self.assertRaisesRegex(RuntimeError, "manifest drift"):
            runner.check_frozen(self.root)


if __name__ == "__main__":
    unittest.main()
