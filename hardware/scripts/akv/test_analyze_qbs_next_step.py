#!/usr/bin/env python3

import csv
import tempfile
import unittest
from pathlib import Path

from analyze_qbs_next_step import (
    parse_trace,
    qwen_context_projection,
    read_single_perf,
    schedule_envelope,
)


class QbsNextStepTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_perf(self, **updates):
        row = {
            "busy_cycles": 100,
            "phase_setup_cycles": 5,
            "phase_activation_cycles": 10,
            "phase_weight_cycles": 15,
            "phase_compute_cycles": 20,
            "phase_overlap_cycles": 30,
            "phase_drain_cycles": 5,
            "phase_scheduler_cycles": 5,
            "phase_commit_cycles": 5,
            "phase_fault_cycles": 0,
            "phase_terminal_cycles": 5,
            "weight_prefetch_wait_cycles": 10,
            "probe_weight_wait_no_outstanding_cycles": 1,
            "probe_weight_wait_response_idle_cycles": 2,
            "probe_weight_wait_r_transfer_cycles": 6,
            "probe_weight_wait_r_blocked_cycles": 1,
            "context_replay_cycles": 4,
            "context_replay_compute_overlap_cycles": 0,
            "dot_active_cycles": 50,
            "weight_bytes": 1000,
            "activation_bytes": 100,
            "payload_bytes": 1100,
            "tiles": 10,
            "probe_profile_result_blocked_cycles": 0,
            "probe_fp_slot_blocked_cycles": 0,
            "probe_fp_accumulator_blocked_cycles": 0,
            "probe_fp_other_blocked_cycles": 0,
            "probe_fp_input_blocked_cycles": 0,
            "probe_read_ar_ready_blocked_cycles": 0,
        }
        row.update(updates)
        path = self.root / "perf.csv"
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        return path

    def test_strict_partitions_and_envelope(self):
        point = read_single_perf(self.write_perf(), "test")
        self.assertAlmostEqual(point["base_schedule_envelope_fraction"], 0.29)
        shapes = [{
            "rank": "1", "profile": "Q4_K", "k": "1024", "m": "1", "n": "32",
            "projected_cycles_no_reuse": "1000",
        }]
        rows, sensitivity, decision = schedule_envelope(shapes, {"Q4_K": point}, 0.40)
        self.assertEqual(rows[0]["context_eligible"], 1)
        self.assertEqual(rows[0]["optimistic_recoverable_cycles"], 330)
        self.assertFalse(sensitivity[1]["meets_10pct_target"])
        self.assertEqual(decision["decision"], "DO_NOT_CHANGE_RTL_FOR_MINIMAL_SCHEDULER")

    def test_rejects_nonexclusive_wait_partition(self):
        with self.assertRaisesRegex(ValueError, "weight-wait partition"):
            read_single_perf(self.write_perf(probe_weight_wait_r_transfer_cycles=5), "test")

    def test_can_report_profile_specific_compute_blocking(self):
        point = read_single_perf(
            self.write_perf(probe_profile_result_blocked_cycles=7),
            "q8",
            require_zero_compute_blocks=False,
        )
        self.assertIn("probe_profile_result_blocked_cycles=7", point["strict_compute_blocked_events"])

    def test_bounded_trace_parser(self):
        path = self.root / "trace.log"
        lines = []
        for cycle in range(200):
            state = 3 if cycle < 180 else 4
            lines.append(f"[QBS_ROOT] c={cycle} cs={state} r=1/1")
        path.write_text("\n".join(lines) + "\n")
        summary, raw = parse_trace(path, "test")
        self.assertEqual(summary["samples"], 200)
        self.assertEqual(summary["r_transfer_samples"], 200)
        self.assertEqual(len(raw), 200)

    def test_context_projection_labels_exact_boundary_as_measured(self):
        rows = [
            {
                "model": "qwen25_1p5b_q4km",
                "effective_kv": str(kv),
                "akv_shape_eligible_compute_nodes": "2",
            }
            for kv in (16, 64, 128, 512)
        ]
        projected = qwen_context_projection(
            rows,
            qbs_cycles=1000,
            rvv_cycles=100,
            akv_points=[(16, 10), (128, 20), (256, 30)],
        )
        kinds = {row["effective_kv"]: row["akv_calibration_kind"] for row in projected}
        self.assertEqual(kinds[16], "measured")
        self.assertEqual(kinds[64], "interpolated")
        self.assertEqual(kinds[128], "measured")
        self.assertEqual(kinds[512], "extrapolated_above")


if __name__ == "__main__":
    unittest.main()
