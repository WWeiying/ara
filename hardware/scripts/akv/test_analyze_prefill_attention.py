#!/usr/bin/env python3

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_prefill_attention as prefill


class AnalyzePrefillAttentionTest(unittest.TestCase):
    def make_tensor(
        self,
        root: Path,
        name: str,
        tensor_type: str,
        shape: list[int],
        element_bytes: int,
        payload: bytes | None = None,
    ) -> str:
        strides = [element_bytes]
        for dimension in range(3):
            strides.append(strides[-1] * shape[dimension])
        nbytes = strides[-1] * shape[-1]
        metadata = root / f"{name}.json"
        metadata.write_text(
            json.dumps(
                {
                    "type": tensor_type,
                    "shape": shape,
                    "strides": strides,
                    "nbytes": nbytes,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        metadata.with_suffix(".bin").write_bytes(payload or bytes(nbytes))
        return metadata.name

    def make_case(self, root: Path, malformed_mask: bool = False) -> Path:
        query = self.make_tensor(root, "query", "f32", [4, 3, 4, 1], 4)
        key = self.make_tensor(root, "key", "f16", [4, 4, 2, 1], 2)
        value = self.make_tensor(root, "value", "f16", [4, 4, 2, 1], 2)
        mask_values = [
            0x0000, 0xFC00, 0xFC00, 0xFC00,
            0x0000, 0x0000, 0xFC00, 0xFC00,
            0x0000, 0x0000, 0x0000, 0xFC00,
        ]
        if malformed_mask:
            mask_values[3] = 0x0000
        mask = self.make_tensor(
            root,
            "mask",
            "f16",
            [4, 3, 1, 1],
            2,
            struct.pack("<12H", *mask_values),
        )
        golden = self.make_tensor(root, "golden", "f32", [16, 3, 1, 1], 4)
        case = root / "case.json"
        case.write_text(
            json.dumps(
                {
                    "kind": "attention_core",
                    "input_a": query,
                    "key": key,
                    "value": value,
                    "mask": mask,
                    "golden": golden,
                    "scale": 0.5,
                    "max_bias": 0.0,
                    "v_transposed": False,
                    "atol": 0.004,
                    "rtol": 0.002,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return case

    def test_exact_work_traffic_and_state(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = prefill.analyze(self.make_case(Path(directory)), [2, 4])
        self.assertEqual(summary["shape"]["active_prefixes"], [1, 2, 3])
        self.assertEqual(summary["work"]["attention_macs"], 192)
        strategies = {entry["name"]: entry for entry in summary["strategies"]}
        self.assertEqual(strategies["rvv_qhead_serial"]["external_kv_bytes"], 384)
        self.assertEqual(strategies["akv_gqa_serial"]["external_kv_bytes"], 192)
        self.assertEqual(
            strategies["akv_resident_single_kv_tile"]["external_kv_bytes"], 96
        )
        self.assertTrue(
            strategies["akv_resident_single_kv_tile"][
                "requires_query_only_context_update"
            ]
        )
        self.assertFalse(
            strategies["akv_resident_single_kv_tile"][
                "requires_concurrent_query_state"
            ]
        )
        self.assertEqual(strategies["akv_query_tile_2"]["external_kv_bytes"], 160)
        self.assertEqual(strategies["akv_query_tile_4"]["external_kv_bytes"], 96)
        self.assertEqual(strategies["unique_kv_floor"]["external_kv_bytes"], 96)
        self.assertEqual(
            strategies["akv_query_tile_4"]["required_q_rows_if_concurrent"], 8
        )
        self.assertTrue(strategies["akv_query_tile_4"]["fits_current_q_rows"])

    def test_rejects_non_prefix_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            case = self.make_case(Path(directory), malformed_mask=True)
            with self.assertRaisesRegex(ValueError, "not a visible-prefix"):
                prefill.analyze(case, [2, 4])

    def test_attaches_passing_cycle_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = prefill.analyze(self.make_case(root), [2, 4])
            rvv_log = root / "rvv.log"
            rvv_log.write_text(
                "LLAMA_OPERATOR operator/prefill/attention_core/rvv "
                "PASS cycles=200 mismatches=0\n",
                encoding="utf-8",
            )
            akv_log = root / "akv.log"
            akv_log.write_text(
                "LLAMA_OPERATOR operator/prefill/attention_core/akv_v2 "
                "PASS cycles=100 mismatches=0\n",
                encoding="utf-8",
            )
            prefill.attach_measurements(
                summary,
                [
                    ("rvv_qhead_serial", rvv_log),
                    ("akv_gqa_serial", akv_log),
                ],
            )
        measurements = {
            entry["strategy"]: entry for entry in summary["measurements"]
        }
        self.assertEqual(measurements["akv_gqa_serial"]["speedup_vs_rvv"], 2.0)
        self.assertEqual(measurements["akv_gqa_serial"]["akv_records"], 0)
        self.assertTrue(summary["decision_gate"]["correctness_gate_pass"])
        self.assertTrue(summary["decision_gate"]["kernel_speedup_gate_pass"])
        self.assertEqual(
            summary["decision_gate"]["overall_status"], "PENDING_MODEL_SHARE"
        )

    def test_aggregates_strict_akv_command_counters(self):
        log = "\n".join(
            [
                "[AKV_PERF] seq=0 success=1 fault=0 busy_cycles=10 "
                "v2_full=1 v2_refill=0 v2_row_load=0 v2_column_load=0 "
                "release=0 q_external_bytes=64 kv_external_bytes=128 "
                "replay_bytes=0 read_outstanding_max=2",
                "[AKV_PERF] seq=1 success=1 fault=0 busy_cycles=3 "
                "v2_full=0 v2_refill=0 v2_row_load=1 v2_column_load=0 "
                "release=0 q_external_bytes=0 kv_external_bytes=0 "
                "replay_bytes=32 read_outstanding_max=1",
            ]
        )
        counters = prefill.parse_akv_perf(log)
        self.assertEqual(counters["records"], 2)
        self.assertEqual(counters["busy_cycles"], 13)
        self.assertEqual(counters["v2_full"], 1)
        self.assertEqual(counters["v2_row_load"], 1)
        self.assertEqual(counters["q_external_bytes"], 64)
        self.assertEqual(counters["kv_external_bytes"], 128)
        self.assertEqual(counters["replay_bytes"], 32)
        self.assertEqual(counters["read_outstanding_max"], 2)

    def test_rejects_faulting_akv_command_record(self):
        with self.assertRaisesRegex(ValueError, "did not complete successfully"):
            prefill.parse_akv_perf(
                "[AKV_PERF] seq=0 success=0 fault=1 busy_cycles=2"
            )


if __name__ == "__main__":
    unittest.main()
