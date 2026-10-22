import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import merge_integrated_final
from run_verilator_coverage import sha256


class IntegratedCoverageMergeTests(unittest.TestCase):
    def test_input_diversity_counts_duplicate_elf_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [root / f"case-{index}.json" for index in range(3)]
            for index, path in enumerate(cases):
                path.write_text(json.dumps({"status": "PASS",
                                            "elf_sha256": "same" if index < 2 else "other"}))
            result = merge_integrated_final.input_diversity(cases)
            self.assertEqual(result["run_count"], 3)
            self.assertEqual(result["unique_elf_count"], 2)
            self.assertEqual(result["duplicate_elf_groups"], [[str(cases[0]), str(cases[1])]])

    def test_source_cases_require_one_image_and_unique_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrices = (("first", 1), ("second", 1))
            for name, _ in matrices:
                merged = root / name / "merged"
                merged.mkdir(parents=True)
                record = {"simv_sha256": "final-image", "cases": [
                    {"result": str(merged / "case.json")} ]}
                (merged / "audit.json").write_text(json.dumps(record))
                independent = {"status": "PASS", "case_count": 1,
                               "merge_audit_sha256": sha256(merged / "audit.json")}
                (merged / "independent_audit.json").write_text(json.dumps(independent))
            with (patch.object(merge_integrated_final, "OUT", root),
                  patch.object(merge_integrated_final, "MATRICES", matrices),
                  patch.object(merge_integrated_final, "audit", return_value={
                      "status": "PASS", "case_count": 1})):
                cases, sources = merge_integrated_final.source_cases()
                self.assertEqual((len(cases), len(sources)), (2, 2))
                second = root / "second" / "merged" / "audit.json"
                value = json.loads(second.read_text())
                value["simv_sha256"] = "old-image"
                second.write_text(json.dumps(value))
                independent = second.parent / "independent_audit.json"
                saved = json.loads(independent.read_text())
                saved["merge_audit_sha256"] = sha256(second)
                independent.write_text(json.dumps(saved))
                with self.assertRaisesRegex(ValueError, "simulator identity"):
                    merge_integrated_final.source_cases()


if __name__ == "__main__":
    unittest.main()
