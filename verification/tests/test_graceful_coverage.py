"""Host-only fake-model tests; never run a processor image."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import run_graceful_coverage as runner

RAW = "# SystemC::Coverage-3\nC '\x01f\x02rtl.sv\x01t\x02line\x01l\x021\x01h\x02tb.dut' 1\n"


class GracefulTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.simv = self.root / "image"
        self.elf = self.root / "source.elf"
        self.reporter = self.root / "reporter"
        for path in (self.simv, self.elf, self.reporter):
            path.write_text(path.name)
        self.output = self.root / "out"
        ref = self.root / "reference"
        ref.mkdir()
        (ref / "sim.log").write_text("reference")
        (ref / "coverage.dat").write_text(RAW)
        self.reference = ref / "result.json"
        self.reference.write_text(json.dumps({"status": "PASS", "self_check_pass": True,
            "simv": str(self.simv), "simv_sha256": runner.sha256(self.simv),
            "elf": str(self.elf), "elf_sha256": runner.sha256(self.elf),
            "sim_log_sha256": runner.sha256(ref / "sim.log"),
            "coverage_sha256": runner.sha256(ref / "coverage.dat")}))

    def fake(self, wall=False, success=False, cycle=False, raw=RAW, code=0, kill=False):
        def run(command, output, timeout, grace):
            log = "Core Test *** SUCCESS *** (tohost = 0)\n" if success else "no completion\n"
            if cycle:
                log += "Simulation timeout of 1388 cycles reached, shutting down simulation.\n"
            (output / "sim.log").write_text(log)
            if raw is not None:
                (output / "coverage.dat").write_text(raw)
            return {"sim_returncode": code, "wall_timeout": wall, "hard_killed": kill,
                    "signals": [{"signal": "SIGINT"}] if wall else [], "simulation_elapsed_s": 0.1}
        return run

    def report(self, reporter, coverage, info, output):
        info.write_text("SF:rtl.sv\nDA:1,1\nend_of_record\n")
        return {"report_returncode": 0, "coverage_info_sha256": runner.sha256(info)}

    def run_case(self, fake, reference=True):
        with patch.object(runner, "run_process", side_effect=fake), \
                patch.object(runner, "report_raw", side_effect=self.report), \
                patch.object(runner.subprocess, "run", side_effect=AssertionError("external command")):
            return runner.run_case(self.simv, self.elf, self.reporter, self.output,
                                   reference=self.reference if reference else None)

    def test_timeout_latched_even_zero_exit_and_late_success_marker(self):
        result = self.run_case(self.fake(wall=True, success=True))
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertTrue(result["raw_valid"])
        self.assertTrue(result["exploration_eligible"])
        self.assertEqual(result["denominator_check"], "PASS")
        self.assertFalse(result["passed_only"])
        self.assertFalse(result["replay_pass_eligible"])
        self.assertEqual(result["grace_s"], 120)

    def test_cycle_stop_is_partial_even_with_success_marker(self):
        result = self.run_case(self.fake(cycle=True, success=True))
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertEqual(result["termination"], "cycle-limit")
        self.assertTrue(result["exploration_eligible"])
        self.assertFalse(result["replay_pass_eligible"])

    def test_natural_pass_still_requires_external_source_audit(self):
        result = self.run_case(self.fake(success=True))
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["replay_pass_eligible"])
        self.assertFalse(result["passed_only"])
        self.assertTrue(result["source_audit_required_for_passed_only"])

    def test_failure_can_have_valid_exploration(self):
        result = self.run_case(self.fake(code=1))
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["exploration_eligible"])

    def test_partial_without_reference_not_merge_eligible(self):
        result = self.run_case(self.fake(wall=True), reference=False)
        self.assertTrue(result["raw_valid"])
        self.assertFalse(result["exploration_eligible"])
        self.assertEqual(result["denominator_check"], "NOT_CHECKED")

    def test_hard_kill_without_raw_retains_timeout(self):
        result = self.run_case(self.fake(wall=True, raw=None, code=-9, kill=True))
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertFalse(result["raw_valid"])
        self.assertFalse(result["exploration_eligible"])

    def test_truncated_raw_is_not_salvaged(self):
        result = self.run_case(self.fake(wall=True, raw=RAW.rstrip("\n")))
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertFalse(result["raw_valid"])
        self.assertIn("incomplete", result["raw_rejection"])

    def test_full_record_but_wrong_denominator_is_not_salvaged(self):
        result = self.run_case(self.fake(wall=True, raw=RAW.replace("rtl.sv", "other.sv")))
        self.assertFalse(result["raw_valid"])
        self.assertIn("denominator mismatch", result["raw_rejection"])

    def test_source_drift_invalidates_salvage(self):
        fake = self.fake(wall=True)
        def drifting(*args):
            result = fake(*args)
            self.elf.write_text("changed")
            return result
        result = self.run_case(drifting)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertTrue(result["infrastructure_errors"])
        self.assertFalse(result["exploration_eligible"])

    def test_mixed_reference_image_prevents_simulation(self):
        saved = json.loads(self.reference.read_text())
        other = self.root / "other-image"
        other.write_text("different image")
        saved.update(simv=str(other), simv_sha256=runner.sha256(other))
        self.reference.write_text(json.dumps(saved))
        with patch.object(runner, "run_process") as process:
            result = runner.run_case(self.simv, self.elf, self.reporter, self.output, reference=self.reference)
            process.assert_not_called()
        self.assertEqual(result["status"], "ERROR")

    def test_real_host_sigint_exits_gracefully(self):
        self.output.mkdir()
        code = ("import signal,time,sys\n"
                "def stop(sig, frame):\n"
                " open('coverage.dat','w').write('saved by handler\\n')\n"
                " sys.exit(0)\n"
                "signal.signal(signal.SIGINT,stop)\n"
                "while True: time.sleep(.01)\n")
        result = runner.run_process([sys.executable, "-c", code], self.output, 0.75, 1)
        self.assertTrue(result["wall_timeout"])
        self.assertFalse(result["hard_killed"])
        self.assertEqual(result["sim_returncode"], 0)
        self.assertEqual([x["signal"] for x in result["signals"]], ["SIGINT"])
        self.assertTrue((self.output / "coverage.dat").exists())

    def test_real_host_ignored_sigint_escalates_and_reaps(self):
        self.output.mkdir()
        code = "import signal,time; signal.signal(signal.SIGINT,signal.SIG_IGN); time.sleep(20)"
        result = runner.run_process([sys.executable, "-c", code], self.output, 0.75, 0.2)
        self.assertTrue(result["hard_killed"])
        self.assertEqual(result["sim_returncode"], -signal.SIGKILL)
        self.assertEqual([x["signal"] for x in result["signals"]], ["SIGINT", "SIGKILL"])
        # This host's signal-zero probe also succeeds for nonexistent PIDs.
        # Verify actual disappearance and that wait() reaped the child instead.
        self.assertFalse(Path(f"/proc/{result['pid']}").exists())
        with self.assertRaises(ChildProcessError):
            os.waitpid(result["pid"], os.WNOHANG)


if __name__ == "__main__":
    unittest.main()
