import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run_handoff as runner
import check_reader_handoff_v2


class BuildAdmissionTests(unittest.TestCase):
    def test_wall_timeout_bounds(self):
        self.assertEqual(runner.SIM_TIMEOUT_SECONDS, 600)
        for seconds in (1, 180, 600):
            runner.validate_timeout(seconds)
        for seconds in (0, 601, True, 180.0, "600"):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                runner.validate_timeout(seconds)

    def test_running_or_failed_build_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            for state, child in (("BUILDING", 3), ("FAIL", None), ("SOC_BUILT_NOT_EXECUTED", 3)):
                (path / "result.json").write_text(json.dumps(dict(state=state, post_pins_match=True)))
                (path / "status.json").write_text(json.dumps(dict(state=state, child_pid=child)))
                with self.subTest(state=state, child=child), self.assertRaises((ValueError, RuntimeError)):
                    runner.checked_soc(path)

    def test_missing_input_pin_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "result.json").write_text(json.dumps(dict(state="SOC_BUILT_NOT_EXECUTED",
                post_pins_match=True, source_pins_sha256="bad")))
            (path / "status.json").write_text(json.dumps(dict(state="SOC_BUILT_NOT_EXECUTED", child_pid=None)))
            (path / "source-pins.json").write_text("{}")
            with self.assertRaises((ValueError, RuntimeError)):
                runner.checked_soc(path)

    def test_no_simulation_without_receipt(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(runner.Execution, "execute") as execute:
            with self.assertRaises(FileNotFoundError):
                runner.checked_soc(Path(temp))
            execute.assert_not_called()


class CorrectedLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (runner.ROOT / "verification/out/reader-handoff-baseline-20261024-01/work/run.vcs.log").read_text()
        cls.rtl = (runner.ROOT / "hardware/src/vlsu/vlsu.sv").read_text()

    def test_actual_baseline_replayed_with_v2(self):
        self.assertIs(runner.log_checker, check_reader_handoff_v2)
        parsed = runner.log_checker.check_log(self.raw, self.rtl)
        self.assertEqual(parsed["state"], "READER_HANDOFF_LOG_V2_CHECKED")
        self.assertEqual(parsed["commands"], 71)
        self.assertEqual(parsed["legacy_commit_words_per_success"], 4)
        with self.assertRaisesRegex(ValueError, "context/atomic commit mismatch"):
            runner.baseline.check_log(self.raw, self.rtl)

    def test_success_four_fault_zero_and_missing_record(self):
        rows = self.raw.splitlines()
        qbs = [i for i, row in enumerate(rows) if row.startswith("[QBS_PERF] ")]
        self.assertEqual(len(qbs), 6)
        for ordinal, index in enumerate(qbs):
            old = "commit_groups=0" if ordinal == 1 else "commit_groups=4"
            self.assertIn(old + " ", rows[index])
            for value in ((1, 4) if ordinal == 1 else (0, 1, 3, 5)):
                bad = list(rows)
                bad[index] = bad[index].replace(old + " ", f"commit_groups={value} ", 1)
                with self.subTest(ordinal=ordinal, value=value), self.assertRaisesRegex(ValueError, "commit-word"):
                    runner.log_checker.check_log("\n".join(bad), self.rtl)
        with self.assertRaises(ValueError):
            runner.log_checker.check_log("\n".join(row for i, row in enumerate(rows) if i != qbs[0]), self.rtl)


if __name__ == "__main__":
    unittest.main()
