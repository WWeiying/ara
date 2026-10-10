import copy
from pathlib import Path
import unittest

import run_gap96_simulation as runner


class Runner96Tests(unittest.TestCase):
    def preflight(self):
        return runner.lifecycle.read_bound(runner.PRE / "preflight-manifest.json", runner.PRE_SEAL)

    def test_exact_rebound_preflight(self):
        runner.validate_preflight(self.preflight())

    def test_reject_contract_mutations(self):
        original = self.preflight()
        for key, value in (("baseline_tests", 701), ("target_unhit_count", 95),
                           ("checks", 0), ("vl", 1), ("expected_vector_instructions", 41),
                           ("expected_vector_bytes", 10751), ("input_elf", "/tmp/other.elf"),
                           ("coverage_admitted", True), ("status", "PASS")):
            bad = copy.deepcopy(original); bad[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                runner.validate_preflight(bad)
        for key in (str(runner.ORIGINAL / "input.elf"), str(runner.ORIGINAL / "spike.trace"),
                    str(runner.PRE / "target-before.json"), str(runner.ORIGINAL / "preflight-manifest.json")):
            bad = copy.deepcopy(original); del bad["pins"][key]
            with self.subTest(pin=key), self.assertRaises(ValueError):
                runner.validate_preflight(bad)

    def test_exact_old_image_trace_coverage_command(self):
        out = runner.OUT / "gap96-unlaunched-unit-test"
        command = runner.command(out)
        self.assertEqual(command[0], str(runner.lifecycle.IMAGE))
        self.assertIn("+PRELOAD=" + str(runner.ORIGINAL / "input.elf"), command)
        self.assertIn("+TESTCASE=" + runner.NAME, command)
        self.assertIn("+COMMIT_TOHOST=80001000", command)
        self.assertIn("+NO_FSDB", command)
        self.assertIn("+COMMIT_TRACE=" + str(out / "commit_trace.csv"), command)
        self.assertIn("+VECTOR_TRACE=" + str(out / "vector_trace.csv"), command)
        self.assertEqual(command[command.index("-cm") + 1], "line+cond+fsm+tgl+branch")
        self.assertEqual(command[command.index("-cm_dir") + 1], str(out / "code.vdb"))
        self.assertEqual(command[command.index("-cm_name") + 1], runner.NAME)

    def test_invalid_output_and_lifecycle_drift_rejected(self):
        from unittest.mock import patch
        for out in (runner.PRE, Path("/tmp/invalid-gap96"), runner.OUT / ".." / "escape"):
            with self.subTest(output=out), self.assertRaises(ValueError):
                runner.prepare(out)
        with patch.object(runner.lifecycle, "digest", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "Frozen95 lifecycle"):
                runner.prepare(runner.OUT / "gap96-unlaunched-unit-test")


if __name__ == "__main__":
    unittest.main()
