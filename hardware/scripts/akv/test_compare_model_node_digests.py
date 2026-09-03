#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("compare-model-node-digests.py")
SPEC = importlib.util.spec_from_file_location("compare_model_node_digests", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def record(node: int, digest: str, op: str = "MUL_MAT") -> str:
    return (
        "GGML_RISCV_MODEL_DIGEST graph=0 "
        f"node={node} op={op} type=F32 ne0=32 ne1=4 ne2=1 ne3=1 "
        f"bytes=512 hash={digest} name=node_{node}\n"
    )


class CompareModelNodeDigestsTest(unittest.TestCase):
    def write(self, root: Path, name: str, text: str) -> Path:
        path = root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_reports_equal_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            text = record(3, "0123456789abcdef") + record(8, "fedcba9876543210")
            report = MODULE.compare_digests(
                self.write(root, "baseline.log", text),
                self.write(root, "candidate.log", text),
            )
            self.assertTrue(report["all_equal"])
            self.assertEqual(report["matching_prefix_records"], 2)
            self.assertIsNone(report["first_mismatch"])

    def test_locates_first_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = record(3, "0123456789abcdef") + record(8, "1111111111111111")
            candidate = record(3, "0123456789abcdef") + record(8, "2222222222222222")
            report = MODULE.compare_digests(
                self.write(root, "baseline.log", baseline),
                self.write(root, "candidate.log", candidate),
            )
            self.assertFalse(report["all_equal"])
            self.assertEqual(report["matching_prefix_records"], 1)
            self.assertEqual(report["first_mismatch"]["node"], 8)

    def test_rejects_different_graph_topology(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "topology differs"):
                MODULE.compare_digests(
                    self.write(root, "baseline.log", record(3, "0123456789abcdef")),
                    self.write(root, "candidate.log", record(3, "0123456789abcdef", "ADD")),
                )


if __name__ == "__main__":
    unittest.main()
