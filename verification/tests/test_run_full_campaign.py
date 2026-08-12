import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from run_full_campaign import (
    MINIMUM_CAMPAIGN_INVENTORY,
    REQUIRED_DIRECTED_TESTS,
    REQUIRED_RANDOM_COVERAGE,
    REQUIRED_RANDOM_PROFILES,
    directed_command,
    random_command,
    source_snapshot,
    validate_inventory,
    validate_random_stimulus_coverage,
    validate_required_directed_tests,
    validate_required_random_profiles,
    write_summary,
)


class FullCampaignCommandTests(unittest.TestCase):
    def test_current_inventory_and_whole_register_corner_are_mandatory(self):
        self.assertEqual(MINIMUM_CAMPAIGN_INVENTORY["rvv"], 200)
        self.assertIn("rvv:vwhole_vstart_edges", REQUIRED_DIRECTED_TESTS)

    def test_source_snapshot_ignores_generated_compiler_macros(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hardware").mkdir()
            (root / "apps").mkdir()
            (root / "verification").mkdir()
            (root / "hardware/design.sv").write_text("module design; endmodule\n")
            generated = root / "apps/compiler_macros.h"
            generated.write_text("#define VLEN 1024\n")

            with mock.patch("run_full_campaign.REPO_ROOT", root):
                before = source_snapshot()
                generated.write_text("#define VLEN 2048\n")
                after = source_snapshot()

            self.assertEqual(before, after)
            self.assertEqual(before["file_count"], 1)

    def test_directed_command_propagates_campaign_timeout(self):
        args = SimpleNamespace(jobs=8, seed=1, timeout=900)
        command = directed_command(Path("out/full"), Path("simv"), args)
        timeout_index = command.index("--timeout")
        self.assertEqual(command[timeout_index + 1], 900)

    def test_random_profiles_enable_exit_and_per_instruction_checks(self):
        args = SimpleNamespace(
            seed=1, timeout=900, spike_timeout=300, watchdog_cycles=100000
        )
        command = random_command(
            "ara_dsa_rvv1_integer_stress",
            Path("out/integer"),
            Path("simv"),
            args,
        )
        self.assertIn("--vector-signature", command)
        self.assertIn("--vector-commit-compare", command)
        self.assertNotIn("--vector-checkpoints", command)

    def test_checkpoint_profiles_keep_checkpoints_and_add_commit_compare(self):
        args = SimpleNamespace(
            seed=1, timeout=900, spike_timeout=300, watchdog_cycles=100000
        )
        command = random_command(
            "ara_dsa_rvv1_checkpoint_regression",
            Path("out/checkpoint"),
            Path("simv"),
            args,
        )
        self.assertIn("--vector-checkpoints", command)
        self.assertIn("--vector-commit-compare", command)

    def test_random_profile_reuses_shared_generator(self):
        args = SimpleNamespace(
            seed=1, timeout=900, spike_timeout=300, watchdog_cycles=100000,
            generator_simv=Path("shared/vcs_simv"),
        )

        command = random_command(
            "ara_dsa_rvv1_arithmetic", Path("out/arithmetic"), Path("simv"), args
        )

        index = command.index("--generator-simv")
        self.assertEqual(command[index + 1], Path("shared/vcs_simv"))

    def test_inventory_allows_added_tests_but_rejects_lost_coverage(self):
        validate_inventory({"rvv": 201, "app": 51, "random": 150, "total": 402})
        with self.assertRaisesRegex(RuntimeError, "below required coverage"):
            validate_inventory({"rvv": 198, "app": 50, "random": 142, "total": 390})

    def test_required_directed_coverage_cannot_be_replaced_by_test_count(self):
        validate_required_directed_tests(set(REQUIRED_DIRECTED_TESTS))
        missing = "rvv:vstore_signature"
        with self.assertRaisesRegex(RuntimeError, missing):
            validate_required_directed_tests(REQUIRED_DIRECTED_TESTS - {missing})

    def test_required_random_profiles_cannot_be_replaced_by_more_nightly_seeds(self):
        profiles = list(REQUIRED_RANDOM_PROFILES.items())
        validate_required_random_profiles(profiles)
        without_fp32 = [item for item in profiles if item[0] != "ara_dsa_rvv1_fp32"]
        without_fp32 = [
            (name, iterations + 10 if name == "ara_dsa_rvv1_nightly" else iterations)
            for name, iterations in without_fp32
        ]
        with self.assertRaisesRegex(RuntimeError, "ara_dsa_rvv1_fp32"):
            validate_required_random_profiles(without_fp32)

    def test_duplicate_random_profile_is_rejected(self):
        profiles = list(REQUIRED_RANDOM_PROFILES.items())
        with self.assertRaisesRegex(RuntimeError, "duplicate random profiles"):
            validate_required_random_profiles([*profiles, profiles[0]])

    def test_random_semantic_coverage_requires_actual_categories(self):
        profiles = [("profile", 2)]
        coverage = {
            "profiles": [{"test": "profile", "source_count": 2}],
            "vector_instruction_count": 100,
            "masked_instruction_count": 1,
            "aggregate": {
                dimension: {name: 1 for name in required}
                for dimension, required in REQUIRED_RANDOM_COVERAGE.items()
            },
        }
        validate_random_stimulus_coverage(coverage, profiles)
        coverage["aggregate"]["memory_modes"]["fault_first"] = 0
        with self.assertRaisesRegex(RuntimeError, "fault_first"):
            validate_random_stimulus_coverage(coverage, profiles)

    def test_random_semantic_coverage_requires_every_generated_source(self):
        profiles = [("profile", 2)]
        coverage = {
            "profiles": [{"test": "profile", "source_count": 1}],
            "vector_instruction_count": 1,
            "masked_instruction_count": 1,
            "aggregate": {},
        }
        with self.assertRaisesRegex(RuntimeError, "profile/source mismatch"):
            validate_random_stimulus_coverage(coverage, profiles)

    def test_complete_campaign_fails_verdict_if_any_test_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rows = [
                {"class": "rvv", "profile": "", "name": "pass", "seed": "",
                 "status": "PASS", "reason": "", "artifact_dir": "pass"},
                {"class": "rvv", "profile": "", "name": "fail", "seed": "",
                 "status": "FAIL", "reason": "mismatch", "artifact_dir": "fail"},
            ]
            expected = {"rvv": 2, "app": 0, "random": 0, "total": 2}
            self.assertFalse(write_summary(output, rows, expected, {}))
            summary = json.loads((output / "campaign_summary.json").read_text())
            self.assertEqual(summary["status"], "COMPLETE")
            self.assertEqual(summary["verdict"], "FAIL")

    def test_complete_all_pass_campaign_has_pass_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rows = [
                {"class": "rvv", "profile": "", "name": "pass", "seed": "",
                 "status": "PASS", "reason": "", "artifact_dir": "pass"},
            ]
            expected = {"rvv": 1, "app": 0, "random": 0, "total": 1}
            self.assertTrue(write_summary(output, rows, expected, {}))
            summary = json.loads((output / "campaign_summary.json").read_text())
            self.assertEqual(summary["verdict"], "PASS")

    def test_duplicate_result_cannot_hide_missing_test(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            row = {"class": "rvv", "profile": "", "name": "same", "seed": "",
                   "status": "PASS", "reason": "", "artifact_dir": "same"}
            expected = {"rvv": 2, "app": 0, "random": 0, "total": 2}
            self.assertFalse(write_summary(output, [row, dict(row)], expected, {}))
            summary = json.loads((output / "campaign_summary.json").read_text())
            self.assertEqual(summary["status"], "INCOMPLETE")
            self.assertEqual(len(summary["duplicate_results"]), 1)

    def test_nonzero_component_exit_forces_fail_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rows = [
                {"class": "rvv", "profile": "", "name": "pass", "seed": "",
                 "status": "PASS", "reason": "", "artifact_dir": "pass"},
            ]
            expected = {"rvv": 1, "app": 0, "random": 0, "total": 1}
            self.assertFalse(write_summary(output, rows, expected, {"rvv": 1}))
            summary = json.loads((output / "campaign_summary.json").read_text())
            self.assertEqual(summary["status"], "COMPLETE")
            self.assertEqual(summary["verdict"], "FAIL")

    def test_one_class_cannot_replace_a_missing_class(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rows = [
                {"class": "rvv", "profile": "", "name": "rvv0", "seed": "",
                 "status": "PASS", "reason": "", "artifact_dir": "rvv0"},
                {"class": "rvv", "profile": "", "name": "rvv1", "seed": "",
                 "status": "PASS", "reason": "", "artifact_dir": "rvv1"},
            ]
            expected = {"rvv": 1, "app": 1, "random": 0, "total": 2}
            self.assertFalse(write_summary(output, rows, expected, {}))
            summary = json.loads((output / "campaign_summary.json").read_text())
            self.assertEqual(summary["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
