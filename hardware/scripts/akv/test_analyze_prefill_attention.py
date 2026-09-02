#!/usr/bin/env python3

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def make_causal_case(
        self,
        root: Path,
        *,
        head_dim: int,
        query_tokens: int,
        query_heads: int,
        kv_heads: int,
        past_tokens: int = 0,
    ) -> Path:
        kv_capacity = past_tokens + query_tokens
        query = self.make_tensor(
            root,
            "query",
            "f32",
            [head_dim, query_tokens, query_heads, 1],
            4,
        )
        key = self.make_tensor(
            root,
            "key",
            "f16",
            [head_dim, kv_capacity, kv_heads, 1],
            2,
        )
        value = self.make_tensor(
            root,
            "value",
            "f16",
            [head_dim, kv_capacity, kv_heads, 1],
            2,
        )
        mask_values = []
        for token in range(query_tokens):
            visible = past_tokens + token + 1
            mask_values.extend(
                0x0000 if column < visible else 0xFC00
                for column in range(kv_capacity)
            )
        mask = self.make_tensor(
            root,
            "mask",
            "f16",
            [kv_capacity, query_tokens, 1, 1],
            2,
            struct.pack(f"<{len(mask_values)}H", *mask_values),
        )
        golden = self.make_tensor(
            root,
            "golden",
            "f32",
            [head_dim * query_heads, query_tokens, 1, 1],
            4,
        )
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
        self.assertEqual(
            strategies["rvv_q64_qhead"]["external_kv_bytes"], 192
        )
        self.assertEqual(strategies["rvv_gqa_q4"]["external_kv_bytes"], 96)
        self.assertEqual(strategies["rvv_gqa_q64"]["external_kv_bytes"], 96)
        self.assertEqual(strategies["akv_gqa_serial"]["external_kv_bytes"], 192)
        self.assertEqual(strategies["akv_query_tile_2"]["external_kv_bytes"], 160)
        self.assertEqual(strategies["akv_query_tile_4"]["external_kv_bytes"], 96)
        self.assertEqual(strategies["unique_kv_floor"]["external_kv_bytes"], 96)
        self.assertEqual(
            strategies["akv_qblock64_kv_outer"]["external_kv_bytes"], 96
        )
        self.assertFalse(
            strategies["akv_qblock64_kv_outer"][
                "requires_query_only_context_update"
            ]
        )
        self.assertTrue(
            strategies["akv_qblock64_kv_outer"][
                "requires_concurrent_query_state"
            ]
        )
        self.assertEqual(
            strategies["akv_qblock64_q2_kv_outer"]["score_f32_bytes"],
            1024,
        )
        self.assertTrue(
            strategies["akv_qblock64_q2_kv_outer"]["fits_current_q_rows"]
        )
        self.assertFalse(
            strategies["akv_qblock64_q2_kv_outer"]["implemented_fast_path"]
        )
        self.assertFalse(
            strategies["akv_qblock64_q2_panel4_kv_outer"][
                "implemented_fast_path"
            ]
        )
        self.assertTrue(
            strategies["akv_qblock64_q2_kv_outer"][
                "requires_concurrent_query_state"
            ]
        )
        self.assertEqual(summary["kv_outer_exact"]["query_block_count"], 1)
        self.assertEqual(
            summary["kv_outer_exact"]["query_blocks"][0]["maximum_prefix"], 3
        )
        self.assertEqual(summary["kv_outer_exact"]["query_tile_visits"], 6)
        self.assertEqual(summary["kv_outer_exact"]["v2_full"], 2)
        self.assertEqual(summary["kv_outer_exact"]["v2_refill"], 0)
        self.assertEqual(summary["kv_outer_exact"]["query_conversions"], 6)
        self.assertEqual(
            summary["kv_outer_exact"]["query_conversion_source_f32_read_bytes"],
            192,
        )
        self.assertEqual(
            summary["kv_outer_exact"]["query_workspace_f16_write_bytes"], 96
        )
        self.assertEqual(
            summary["kv_outer_exact"]["ordinary_qk_query_read_bytes"], 96
        )
        self.assertEqual(
            summary["kv_outer_exact"]["resident_query_fill_bytes"], 32
        )
        self.assertEqual(
            summary["kv_outer_exact"]["total_query_traffic_bytes"], 416
        )
        self.assertEqual(
            summary["kv_outer_exact"]["active_output_numerator_f32_bytes"], 96
        )
        self.assertEqual(
            summary["kv_outer_exact"]["active_softmax_state_f32_bytes"], 48
        )
        self.assertEqual(
            summary["kv_outer_exact"]["state_scalar_read_write_bytes"], 192
        )
        self.assertEqual(
            summary["kv_outer_exact"]["state_numerator_read_write_bytes"], 384
        )
        self.assertEqual(
            summary["kv_outer_exact"]["initial_state_write_bytes"], 288
        )
        self.assertEqual(
            summary["kv_outer_exact"]["final_output_read_write_bytes"], 384
        )
        self.assertEqual(
            summary["kv_outer_exact"]["final_softmax_sum_read_bytes"], 48
        )
        self.assertEqual(
            summary["kv_outer_exact"]["allocated_workspace_bytes"], 139520
        )
        vslice = summary["kv_outer_q2_panel4_vslice64_exact"]
        self.assertFalse(vslice["supported_shape"])
        self.assertEqual(vslice["q2_shared_v_rows"], 2)
        self.assertEqual(vslice["single_query_v_rows"], 8)
        self.assertEqual(vslice["v2_row_load"], 12)
        self.assertEqual(vslice["row_replay_bytes"], 80)
        self.assertIsNone(vslice["row_busy_cycle_model"])
        self.assertEqual(summary["kv_outer_exact"]["column_replay_bytes"], 144)
        self.assertEqual(summary["kv_outer_exact"]["row_replay_bytes"], 96)
        self.assertEqual(summary["kv_outer_exact"]["replay_bytes"], 240)
        self.assertEqual(summary["kv_outer_exact"]["command_records"], 40)
        q2 = summary["kv_outer_q2_exact"]
        self.assertFalse(q2["supported_shape"])
        self.assertEqual(q2["query_group_visits_per_kv_head"], 2)
        self.assertEqual(q2["query_group_visits"], 4)
        self.assertEqual(q2["v2_column_load"], 16)
        self.assertEqual(q2["v2_row_load"], 12)
        self.assertEqual(q2["column_replay_bytes"], 96)
        self.assertEqual(q2["row_replay_bytes"], 96)
        self.assertEqual(q2["replay_bytes"], 192)
        self.assertEqual(q2["command_records"], 32)
        panel4 = summary["kv_outer_q2_panel4_exact"]
        self.assertFalse(panel4["supported_shape"])
        self.assertEqual(panel4["column_panel_width"], 4)
        self.assertEqual(panel4["q2_pair_visits"], 2)
        self.assertEqual(panel4["q1_fallback_visits"], 2)
        self.assertEqual(panel4["v2_column_load"], 10)
        self.assertEqual(panel4["v2_column_panel"], 2)
        self.assertEqual(panel4["v2_logical_column"], 16)
        self.assertEqual(panel4["v2_k_view_bank_cycles"], 10)
        self.assertEqual(panel4["v2_row_load"], 12)
        self.assertEqual(panel4["replay_bytes"], 192)
        self.assertEqual(panel4["command_records"], 26)
        self.assertEqual(
            strategies["akv_query_tile_4"]["required_q_rows_if_concurrent"], 8
        )
        self.assertTrue(strategies["akv_query_tile_4"]["fits_current_q_rows"])

    def test_panel4_distinguishes_q2_pairs_from_q1_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            odd = prefill.analyze(
                self.make_causal_case(
                    root,
                    head_dim=128,
                    query_tokens=15,
                    query_heads=12,
                    kv_heads=2,
                ),
                [2, 4, 64],
            )["kv_outer_q2_panel4_exact"]

        self.assertTrue(odd["supported_shape"])
        self.assertEqual(odd["query_group_visits_per_kv_head"], 8)
        self.assertEqual(odd["q2_pair_visits_per_kv_head"], 7)
        self.assertEqual(odd["q1_fallback_visits_per_kv_head"], 1)
        self.assertEqual(odd["q2_pair_visits"], 14)
        self.assertEqual(odd["q1_fallback_visits"], 2)
        self.assertEqual(odd["v2_column_load"], 704)
        self.assertEqual(odd["v2_column_panel"], 448)
        self.assertEqual(odd["v2_logical_column"], 2048)
        self.assertEqual(odd["v2_k_view_bank_cycles"], 1408)
        self.assertEqual(odd["replay_bytes"], 122880)
        self.assertEqual(odd["command_records"], 948)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            even = prefill.analyze(
                self.make_causal_case(
                    root,
                    head_dim=128,
                    query_tokens=16,
                    query_heads=12,
                    kv_heads=2,
                ),
                [2, 4, 64],
            )["kv_outer_q2_panel4_exact"]

        self.assertEqual(even["q2_pair_visits"], 16)
        self.assertEqual(even["q1_fallback_visits"], 0)
        self.assertEqual(even["v2_column_load"], 512)
        self.assertEqual(even["v2_column_panel"], 512)
        self.assertEqual(even["v2_logical_column"], 2048)
        self.assertEqual(even["v2_k_view_bank_cycles"], 1024)
        self.assertEqual(even["replay_bytes"], 135168)
        self.assertEqual(even["command_records"], 788)

    def test_rejects_non_prefix_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            case = self.make_case(Path(directory), malformed_mask=True)
            with self.assertRaisesRegex(ValueError, "not a visible-prefix"):
                prefill.analyze(case, [2, 4])

    def test_rejects_nonfinite_visible_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.make_case(root)
            mask_path = root / "mask.bin"
            values = list(struct.unpack("<12H", mask_path.read_bytes()))
            values[0] = 0x7E00
            mask_path.write_bytes(struct.pack("<12H", *values))
            with self.assertRaisesRegex(ValueError, "contains NaN or infinity"):
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

    def test_speedup_gate_uses_fastest_measured_rvv_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = prefill.analyze(self.make_case(root), [2, 4])
            logs = {}
            for strategy, cycles in (
                ("rvv_qhead_serial", 200),
                ("rvv_q64_qhead", 150),
                ("rvv_gqa_q4", 120),
                ("rvv_gqa_q64", 110),
                ("akv_qblock64_kv_outer", 100),
            ):
                path = root / f"{strategy}.log"
                path.write_text(
                    "LLAMA_OPERATOR operator/prefill/attention_core/test "
                    f"PASS cycles={cycles} mismatches=0\n",
                    encoding="utf-8",
                )
                logs[strategy] = path

            exact = summary["kv_outer_exact"]
            akv_fields = {
                "v2_full": exact["v2_full"],
                "v2_refill": exact["v2_refill"],
                "v2_column_load": exact["v2_column_load"],
                "v2_row_load": exact["v2_row_load"],
                "release": exact["v2_release"],
                "q_external_bytes": exact["resident_query_fill_bytes"],
                "kv_external_bytes": exact["external_kv_bytes"],
                "replay_bytes": exact["replay_bytes"],
            }
            logs["akv_qblock64_kv_outer"].write_text(
                logs["akv_qblock64_kv_outer"].read_text(encoding="utf-8")
                + "\n".join(
                    "[AKV_PERF] seq=%d success=1 fault=0 %s"
                    % (
                        index,
                        " ".join(
                            f"{field}={value if index == 0 else 0}"
                            for field, value in akv_fields.items()
                        ),
                    )
                    for index in range(exact["command_records"])
                )
                + "\n",
                encoding="utf-8",
            )
            prefill.attach_measurements(summary, list(logs.items()))

        entries = {entry["strategy"]: entry for entry in summary["measurements"]}
        self.assertEqual(
            summary["decision_gate"]["strongest_rvv_strategy"],
            "rvv_gqa_q64",
        )
        self.assertEqual(summary["decision_gate"]["strongest_rvv_cycles"], 110)
        self.assertAlmostEqual(
            entries["akv_qblock64_kv_outer"]["speedup_vs_strongest_rvv"], 1.1
        )
        self.assertFalse(summary["decision_gate"]["kernel_speedup_gate_pass"])

    def test_selects_fastest_retained_akv_and_rejects_vslice_experiment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = prefill.analyze(self.make_case(root), [2, 4])
            specs = []
            for strategy, cycles in (
                ("rvv_gqa_q64", 120),
                ("akv_gqa_serial", 110),
                ("akv_qblock64_q2_panel4_kv_outer", 90),
                (prefill.VSLICE64_STRATEGY, 95),
            ):
                path = root / f"{strategy}.log"
                path.write_text(
                    "LLAMA_OPERATOR operator/prefill/attention_core/test "
                    f"PASS cycles={cycles} mismatches=0\n",
                    encoding="utf-8",
                )
                specs.append((strategy, path))
            with mock.patch.object(
                prefill, "validate_kv_outer_counters", return_value={}
            ):
                prefill.attach_measurements(summary, specs)

        self.assertEqual(
            summary["decision_gate"]["retained_akv_strategy"],
            "akv_qblock64_q2_panel4_kv_outer",
        )
        self.assertEqual(summary["decision_gate"]["retained_akv_cycles"], 90)
        experiment = summary["vslice64_experiment"]
        self.assertAlmostEqual(experiment["cycle_change_vs_panel4"], 95 / 90 - 1)
        self.assertEqual(
            experiment["retention_status"],
            "REJECTED_M15_RTL_REGRESSION",
        )

    def test_aggregates_strict_akv_command_counters(self):
        log = "\n".join(
            [
                "[AKV_PERF] seq=0 success=1 fault=0 busy_cycles=10 "
                "v2_full=1 v2_refill=0 v2_row_load=0 v2_column_load=0 "
                "v2_column_panel=0 v2_logical_column=0 "
                "v2_k_view_bank_cycles=0 "
                "release=0 q_external_bytes=64 kv_external_bytes=128 "
                "replay_bytes=0 read_outstanding_max=2",
                "[AKV_PERF] seq=1 success=1 fault=0 busy_cycles=3 "
                "v2_full=0 v2_refill=0 v2_row_load=1 v2_column_load=0 "
                "v2_column_panel=0 v2_logical_column=0 "
                "v2_k_view_bank_cycles=0 "
                "release=0 q_external_bytes=0 kv_external_bytes=0 "
                "replay_bytes=32 read_outstanding_max=1",
            ]
        )
        counters = prefill.parse_akv_perf(log)
        self.assertEqual(counters["records"], 2)
        self.assertEqual(counters["busy_cycles"], 13)
        self.assertEqual(counters["v2_full"], 1)
        self.assertEqual(counters["v2_row_load"], 1)
        self.assertEqual(counters["v2_column_panel"], 0)
        self.assertEqual(counters["q_external_bytes"], 64)
        self.assertEqual(counters["kv_external_bytes"], 128)
        self.assertEqual(counters["replay_bytes"], 32)
        self.assertEqual(counters["read_outstanding_max"], 2)

    def test_parses_strict_akv_summary(self):
        fields = {field: 0 for field in prefill.AKV_SUM_FIELDS}
        fields.update({
            "records": 948,
            "success_records": 948,
            "fault_records": 0,
            "validation_fault_records": 0,
            "busy_cycles": 1234,
            "v2_column_load": 704,
            "v2_column_panel": 448,
            "v2_logical_column": 2048,
            "v2_k_view_bank_cycles": 1408,
            "replay_bytes": 122880,
            "read_outstanding_max": 2,
        })
        log = "[AKV_PERF_SUMMARY] " + " ".join(
            f"{field}={value}" for field, value in fields.items()
        )
        counters = prefill.parse_akv_perf(log)
        self.assertEqual(counters["records"], 948)
        self.assertEqual(counters["success_records"], 948)
        self.assertEqual(counters["v2_column_panel"], 448)
        self.assertEqual(counters["replay_bytes"], 122880)
        self.assertEqual(counters["read_outstanding_max"], 2)

    def test_rejects_incomplete_or_failed_akv_summary(self):
        with self.assertRaisesRegex(ValueError, "missing fields"):
            prefill.parse_akv_perf(
                "[AKV_PERF_SUMMARY] records=1 success_records=1 "
                "fault_records=0 validation_fault_records=0"
            )

        fields = {field: 0 for field in prefill.AKV_SUM_FIELDS}
        fields.update({
            "records": 1,
            "success_records": 0,
            "fault_records": 1,
            "validation_fault_records": 0,
            "read_outstanding_max": 0,
        })
        log = "[AKV_PERF_SUMMARY] " + " ".join(
            f"{field}={value}" for field, value in fields.items()
        )
        with self.assertRaisesRegex(ValueError, "failed commands"):
            prefill.parse_akv_perf(log)

    def test_rejects_mixed_akv_perf_modes(self):
        with self.assertRaisesRegex(ValueError, "mixes detailed and summary"):
            prefill.parse_akv_perf(
                "[AKV_PERF] seq=0 success=1 fault=0\n"
                "[AKV_PERF_SUMMARY] records=1"
            )

    def test_attaches_llm_microarchitecture_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = prefill.analyze(self.make_case(root), [2, 4])
            report = root / "llm_perf_report_test.log"
            report.write_text(
                "[LLM_PERF] case=test phase=total nr_lanes=4 cycles=200 "
                "backend_busy_cycles=160 lane_active_cycles=100 "
                "compute_active_cycles=80 mfpu_exec_active_cycles=60 "
                "mfpu_exec_lane_fires=220 req_valid_cycles=120 "
                "req_fire_count=40 req_blocked_cycles=80 queue_full_cycles=20 "
                "queue_resource_block_cycles=10 operand_block_cycles=8 "
                "hazard_block_cycles=6\n"
                "[LLM_PERF] case=test phase=quantize nr_lanes=4 cycles=10\n"
                "[LLM_PERF] case=test phase=pack nr_lanes=4 cycles=20\n"
                "[LLM_PERF] case=test phase=matmul nr_lanes=4 cycles=170\n",
                encoding="utf-8",
            )
            log = root / "rvv.log"
            log.write_text(
                "LLAMA_OPERATOR operator/prefill/attention_core/test "
                "PASS cycles=200 mismatches=0\n"
                f"[LLM_PERF] wrote {report.name}\n",
                encoding="utf-8",
            )
            prefill.attach_measurements(summary, [("rvv_qhead_serial", log)])

        entry = summary["measurements"][0]
        self.assertEqual(entry["llm_mfpu_exec_lane_fires"], 220)
        self.assertEqual(entry["llm_perf"]["phases"]["matmul"]["cycles"], 170)
        self.assertAlmostEqual(entry["llm_lane_active_ratio"], 0.5)
        self.assertAlmostEqual(entry["llm_mfpu_active_ratio"], 0.3)
        self.assertAlmostEqual(entry["llm_request_blocked_ratio"], 0.4)
        self.assertAlmostEqual(entry["llm_queue_full_ratio"], 0.1)

    def test_rejects_missing_llm_microarchitecture_report(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            with self.assertRaisesRegex(ValueError, "missing LLM performance report"):
                prefill.load_llm_perf(
                    log, "[LLM_PERF] wrote llm_perf_report_missing.log\n"
                )

    def test_validates_kv_outer_schedule_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = prefill.analyze(self.make_case(Path(directory)), [2, 4])
        exact = summary["kv_outer_exact"]
        counters = {
            "v2_full": exact["v2_full"],
            "v2_refill": exact["v2_refill"],
            "v2_column_load": exact["v2_column_load"],
            "v2_row_load": exact["v2_row_load"],
            "release": exact["v2_release"],
            "q_external_bytes": exact["resident_query_fill_bytes"],
            "kv_external_bytes": exact["external_kv_bytes"],
            "replay_bytes": exact["replay_bytes"],
            "records": exact["command_records"],
        }
        status = prefill.validate_kv_outer_counters(
            summary, "akv_qblock64_kv_outer", counters
        )
        self.assertEqual(status["strict_counter_status"], "PASS")
        counters["v2_column_load"] -= 1
        with self.assertRaisesRegex(ValueError, "strict AKV counters"):
            prefill.validate_kv_outer_counters(
                summary, "akv_qblock64_kv_outer", counters
            )

        q2 = summary["kv_outer_q2_exact"]
        q2_counters = {
            "v2_full": q2["v2_full"],
            "v2_refill": q2["v2_refill"],
            "v2_column_load": q2["v2_column_load"],
            "v2_row_load": q2["v2_row_load"],
            "release": q2["v2_release"],
            "q_external_bytes": q2["resident_query_fill_bytes"],
            "kv_external_bytes": q2["external_kv_bytes"],
            "replay_bytes": q2["replay_bytes"],
            "records": q2["command_records"],
        }
        status = prefill.validate_kv_outer_counters(
            summary, "akv_qblock64_q2_kv_outer", q2_counters
        )
        self.assertEqual(status["strict_counter_status"], "PASS")
        q2_counters["replay_bytes"] += 2
        with self.assertRaisesRegex(ValueError, "strict AKV counters"):
            prefill.validate_kv_outer_counters(
                summary, "akv_qblock64_q2_kv_outer", q2_counters
            )

        panel4 = summary["kv_outer_q2_panel4_exact"]
        panel4_counters = {
            "v2_full": panel4["v2_full"],
            "v2_refill": panel4["v2_refill"],
            "v2_column_load": panel4["v2_column_load"],
            "v2_column_panel": panel4["v2_column_panel"],
            "v2_logical_column": panel4["v2_logical_column"],
            "v2_k_view_bank_cycles": panel4["v2_k_view_bank_cycles"],
            "v2_bank_conflict_cycles": 0,
            "v2_rejected": 0,
            "v2_row_load": panel4["v2_row_load"],
            "release": panel4["v2_release"],
            "q_external_bytes": panel4["resident_query_fill_bytes"],
            "kv_external_bytes": panel4["external_kv_bytes"],
            "replay_bytes": panel4["replay_bytes"],
            "records": panel4["command_records"],
        }
        status = prefill.validate_kv_outer_counters(
            summary, "akv_qblock64_q2_panel4_kv_outer", panel4_counters
        )
        self.assertEqual(status["strict_counter_status"], "PASS")
        self.assertEqual(status["strict_counter_checked_fields"], 14)
        panel4_counters["v2_logical_column"] -= 1
        with self.assertRaisesRegex(ValueError, "strict AKV counters"):
            prefill.validate_kv_outer_counters(
                summary,
                "akv_qblock64_q2_panel4_kv_outer",
                panel4_counters,
            )

        vslice = summary["kv_outer_q2_panel4_vslice64_exact"]
        vslice_counters = {
            "v2_full": vslice["v2_full"],
            "v2_refill": vslice["v2_refill"],
            "v2_column_load": vslice["v2_column_load"],
            "v2_column_panel": vslice["v2_column_panel"],
            "v2_logical_column": vslice["v2_logical_column"],
            "v2_k_view_bank_cycles": vslice["v2_k_view_bank_cycles"],
            "v2_bank_conflict_cycles": 0,
            "v2_rejected": 0,
            "v2_row_load": vslice["v2_row_load"],
            "release": vslice["v2_release"],
            "q_external_bytes": vslice["resident_query_fill_bytes"],
            "kv_external_bytes": vslice["external_kv_bytes"],
            "replay_bytes": vslice["replay_bytes"],
            "records": vslice["command_records"],
        }
        status = prefill.validate_kv_outer_counters(
            summary,
            "akv_qblock64_q2_panel4_vslice64_kv_outer",
            vslice_counters,
        )
        self.assertEqual(status["strict_counter_status"], "PASS")
        self.assertEqual(status["strict_counter_checked_fields"], 14)
        vslice_counters["replay_bytes"] += 128
        with self.assertRaisesRegex(ValueError, "strict AKV counters"):
            prefill.validate_kv_outer_counters(
                summary,
                "akv_qblock64_q2_panel4_vslice64_kv_outer",
                vslice_counters,
            )

    def test_rejects_faulting_akv_command_record(self):
        with self.assertRaisesRegex(ValueError, "did not complete successfully"):
            prefill.parse_akv_perf(
                "[AKV_PERF] seq=0 success=0 fault=1 busy_cycles=2"
            )


if __name__ == "__main__":
    unittest.main()
