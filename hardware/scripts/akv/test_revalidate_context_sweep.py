#!/usr/bin/env python3

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("revalidate-context-sweep.py")
SPEC = importlib.util.spec_from_file_location("revalidate_context_sweep", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RevalidateContextSweepTest(unittest.TestCase):
    def test_summary_separates_execute_and_shape_fallback(self):
        manifest = {"models": [{"id": "a"}, {"id": "b"}], "kv_lengths": [16, 128]}
        rows = []
        for model, eligible, fallback in (("a", 3, 0), ("b", 0, 2)):
            for kv in manifest["kv_lengths"]:
                rows.append({
                    "model": model,
                    "effective_kv": kv,
                    "status": "PASS",
                    "akv_candidate_compute_nodes": eligible + fallback,
                    "akv_shape_eligible_compute_nodes": eligible,
                    "akv_shape_fallback_compute_nodes": fallback,
                })
        support = [
            {
                "model": "a", "model_name": "A", "head_dims": "64",
                "gqa_rows": "3", "observed_disposition": "execute",
                "host_census_status": "PASS",
            },
            {
                "model": "b", "model_name": "B", "head_dims": "256",
                "gqa_rows": "4", "observed_disposition": "fallback_shape",
                "host_census_status": "PASS",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / name for name in ("provenance.json", "counts.csv", "support.csv")]
            for path in paths:
                path.write_text(path.name + "\n", encoding="utf-8")
            summary = MODULE.build_summary(manifest, rows, support, *paths)

        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["case_count"], 4)
        self.assertEqual(summary["model_dispositions"], {"execute": 1, "fallback_shape": 1})
        self.assertEqual(summary["candidate_nodes_across_cases"], 10)
        self.assertEqual(summary["eligible_nodes_across_cases"], 6)
        self.assertEqual(summary["fallback_nodes_across_cases"], 4)
        self.assertIn("not QEMU execution", summary["scope"])

    def test_summary_rejects_incomplete_case_matrix(self):
        manifest = {"models": [{"id": "a"}], "kv_lengths": [16, 128]}
        rows = [{
            "status": "PASS", "akv_candidate_compute_nodes": 1,
            "akv_shape_eligible_compute_nodes": 1,
            "akv_shape_fallback_compute_nodes": 0,
        }]
        with self.assertRaisesRegex(ValueError, "expected 2"):
            MODULE.build_summary(manifest, rows, [], Path("a"), Path("b"), Path("c"))


if __name__ == "__main__":
    unittest.main()
