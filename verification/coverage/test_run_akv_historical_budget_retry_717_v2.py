import unittest
from unittest.mock import patch

import akv_historical_budget_source_proof_717 as source
import run_akv_historical_budget_retry_717_v2 as v2


class SuccessorTests(unittest.TestCase):
    def test_translation_csr_write_vs_read(self):
        self.assertTrue(source.writes_translation_csr(0x18051073))
        self.assertFalse(source.writes_translation_csr(0x18002573))
        self.assertTrue(source.writes_translation_csr(0x28005073))
        self.assertFalse(source.writes_translation_csr(0x0005345b))

    def test_both_real_elfs_are_statically_bare(self):
        for name, (producer, _, _, _) in v2.base.CASES.items():
            elf = v2.base.OUT / producer / "results" / name / "tests" / ("app_" + name) / "input.elf"
            self.assertEqual(source.elf_no_translation_writes(elf.read_bytes())["translation_csr_writes"], 0)

    def test_source_proof_not_just_measured_zero(self):
        elf = v2.base.OUT / "gap48-current-20261004-01/results/akv_gap46_skew_context/tests/app_akv_gap46_skew_context/input.elf"
        proof, pins = source.source_proof(elf)
        self.assertFalse(proof["measured_zero_used_as_only_justification"])
        self.assertEqual(len(proof["bindings"]), 7)
        self.assertEqual([p["phase"] for p in proof["old_new_differences"]], [1, 8])
        self.assertIn(str(source.BUILD_PINS), pins)

    def test_parallel_wording_and_no_frozen_mutation(self):
        manifest = dict(pins={}, schema="old", input_elf="mock", environment_review={"concurrency": "old serial"}, tool_issue_record={})
        original = v2.base.prepare
        with patch.object(v2.base, "prepare", return_value=(v2.base.OUT / "mock", manifest)), \
                patch.object(source, "source_proof", return_value=({}, {})), \
                patch.object(v2.base, "check_pins"):
            _, result = v2.prepare(source.oracle.DESCRIPTOR, v2.base.OUT / "mock")
        self.assertIn("may run in parallel", result["environment_review"]["concurrency"])
        self.assertIs(v2.base.prepare, original)


if __name__ == "__main__":
    unittest.main()
