import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))

from audit_final_rvv_activity import union_axis, verify_case_hashes
from run_verilator_coverage import sha256


class FinalRvvActivityTests(unittest.TestCase):
    def test_union_requires_same_targets_and_actual_retirement(self):
        first = {"bins": {"a": {"retired_instructions": 2},
                          "b": {"retired_instructions": 0}}}
        second = {"bins": {"a": {"retired_instructions": 0},
                           "b": {"retired_instructions": 3}}}
        self.assertEqual(union_axis(first, second), {
            "target_bins": 2, "observed_bins": 2, "unobserved_bins": []})
        second["bins"]["b"]["retired_instructions"] = 0
        self.assertEqual(union_axis(first, second)["unobserved_bins"], ["b"])
        del second["bins"]["b"]
        with self.assertRaises(ValueError):
            union_axis(first, second)

    def test_case_hashes_reject_mutated_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            case.mkdir()
            objdump = case / "objdump"
            for path in (case / "input.elf", objdump,
                         case / "ara_commit_trace.csv", case / "result.json"):
                path.write_text("frozen")
            paths = {"elf": case / "input.elf", "objdump": objdump,
                     "commit_trace": case / "ara_commit_trace.csv",
                     "result": case / "result.json"}
            record = {"case": str(case), "evidence_kind": "random_spike_complete_result",
                      "sha256": {name: sha256(path) for name, path in paths.items()}}
            verify_case_hashes(record, objdump)
            (case / "ara_commit_trace.csv").write_text("mutated")
            with self.assertRaisesRegex(ValueError, "evidence changed"):
                verify_case_hashes(record, objdump)


if __name__ == "__main__":
    unittest.main()
