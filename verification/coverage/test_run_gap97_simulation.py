"""Gap97 runner gates, including prepare-only mode; no EDA execution."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import run_gap97_simulation as runner


class Runner97Tests(unittest.TestCase):
    def preflight(self):
        return runner.lifecycle.read_bound(runner.PRE / "preflight-manifest.json", runner.PRE_SEAL)

    def test_exact_actual_preflight(self):
        runner.validate_preflight(self.preflight())

    def test_reject_contract_and_signature_mutations(self):
        original = self.preflight()
        for key, value in (("baseline_tests", 704), ("target_unhit_count", 5), ("checks", 74),
                           ("expected_vector_data_requests", 1), ("expected_vector_data_bytes", 1),
                           ("expected_vsetvli", 0), ("coverage_admitted", True),
                           ("rtl_changed", True), ("status", "PASS")):
            bad = copy.deepcopy(original)
            bad[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                runner.validate_preflight(bad)
        for key, value in (("checks", 74), ("csr_phases", 9), ("exact_observed_bytes", 592),
                           ("probe_counts", {})):
            bad = copy.deepcopy(original)
            bad["spike_validation"][key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                runner.validate_preflight(bad)
        bad = copy.deepcopy(original)
        bad["symbols"]["tohost"] = 0
        with self.assertRaises(ValueError):
            runner.validate_preflight(bad)

    def test_missing_or_changed_bound_artifact_rejected(self):
        original = self.preflight()
        for name in ("input.elf", "target-before.json", "frozen-ara_dispatcher.sv", "spike.trace",
                     "spike-validation.json", "input.objdump", "compile-command.json", "spike-command.json"):
            bad = copy.deepcopy(original)
            del bad["pins"][str(runner.PRE / name)]
            with self.subTest(name=name), self.assertRaises(ValueError):
                runner.validate_preflight(bad)
        bad = copy.deepcopy(original)
        bad["pins"][str(runner.PRE / "input.elf")] = "0" * 64
        with self.assertRaises(ValueError):
            runner.validate_preflight(bad)

    def test_exact_command(self):
        output = runner.OUT / "unlaunched-gap97-test"
        self.assertEqual(runner.command(output),
            [str(runner.lifecycle.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
             "+PRELOAD=" + str(runner.PRE / "input.elf"), "+TESTCASE=" + runner.NAME,
             "+COMMIT_TOHOST=80001000", "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
             "+VECTOR_TRACE=" + str(output / "vector_trace.csv"), "-cm", "line+cond+fsm+tgl+branch",
             "-cm_dir", str(output / "code.vdb"), "-cm_name", runner.NAME])

    def test_fresh_output_and_frozen_lifecycle_gates(self):
        for output in (runner.PRE, Path("/tmp/gap97-rejected"), runner.OUT / ".." / "escape"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                runner.prepare(output)
        with patch.object(runner.lifecycle, "digest", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "Frozen95 lifecycle"):
                runner.prepare(runner.OUT / "unlaunched-gap97-test")

    def test_prepare_mode_never_calls_run(self):
        output = runner.OUT / "unlaunched-gap97-test"
        with patch.object(runner, "prepare", return_value=(output, {"pins": {}})), \
                patch.object(runner.lifecycle, "save") as save, \
                patch.object(runner.lifecycle, "digest", return_value="a" * 64), \
                patch.object(runner.lifecycle, "run") as launch:
            runner.main(["prepare", "--output", str(output)])
            save.assert_called_once_with(runner.prepared_path(output), {"pins": {}})
            launch.assert_not_called()

    def test_run_requires_reviewed_seal_and_equal_contract(self):
        output = runner.OUT / "unlaunched-gap97-test"
        with patch.object(runner.lifecycle, "run") as launch:
            with self.assertRaises(SystemExit):
                runner.main(["run", "--output", str(output)])
            launch.assert_not_called()
        with patch.object(runner, "prepare", return_value=(output, {"command": ["expected"]})), \
                patch.object(runner.lifecycle, "read_bound", return_value={"command": ["wrong"]}), \
                patch.object(runner.lifecycle, "run") as launch:
            with self.assertRaisesRegex(ValueError, "contract changed"):
                runner.main(["run", "--output", str(output), "--prepared-seal", "a" * 64])
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
