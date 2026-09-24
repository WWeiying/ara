#!/usr/bin/env python3
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "software"))
import host_axi_counter_probe as probe


def snap(sequence, ar, r_bytes):
    return {"snapshot_sequence": sequence, "watchdog_snapshot": False,
            "ddr1": {"ar_count": ar, "r_bytes": r_bytes, "last_ar_addr": 0,
                     "read_outstanding": 0, "error_count": 0}}


class Memory:
    def __init__(self):
        self.calls = []

    def exchange(self, operations):
        for op in operations:
            self.calls.append(op)
            if op.bus != "M" or op.kind != "READ" or op.address != probe.ADDRESSES[op.burst]:
                raise AssertionError("Only the selected memory address may be read")
            op.wire()
        return [bytes(16)]


class ProbeTests(unittest.TestCase):
    def test_counter_deltas_and_order(self):
        memory = Memory()
        report = {"reads": []}
        with patch.object(probe, "identity", return_value={"caps": 1}), \
             patch.object(probe, "read_debug", return_value=[7]), \
             patch.object(probe, "capture_snapshot",
                          side_effect=[snap(1, 10, 80), snap(2, 10, 80),
                                       snap(3, 11, 96), snap(4, 12, 112)]):
            probe.collect(memory, report)
        self.assertEqual([op.burst for op in memory.calls], ["FIXED", "INCR"])
        self.assertEqual(report["idle_ar_delta"], 0)
        self.assertEqual([row["delta"] for row in report["reads"]],
                         [{"ar_count": 1, "r_bytes": 16, "error_count": 0}] * 2)

    def test_idle_activity_blocks_probe(self):
        memory = Memory()
        with patch.object(probe, "identity", return_value={"caps": 1}), \
             patch.object(probe, "read_debug", return_value=[7]), \
             patch.object(probe, "capture_snapshot",
                          side_effect=[snap(1, 10, 80), snap(2, 11, 88)]):
            with self.assertRaisesRegex(RuntimeError, "changed while idle"):
                probe.collect(memory, {"reads": []})
        self.assertEqual(memory.calls, [])

    def test_partial_failure_keeps_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            with patch.object(probe, "VivadoTransport") as transport, \
                 patch.object(probe, "identity", return_value={"caps": 1}), \
                 patch.object(probe, "read_debug", return_value=[6]), \
                 contextlib.redirect_stdout(io.StringIO()):
                transport.return_value.__enter__.return_value = Memory()
                with self.assertRaisesRegex(RuntimeError, "not ready"):
                    probe.main("dummy.ltx", output)
            report = json.loads((output / "counter_probe.json").read_text())
            self.assertFalse(report["memory_writes"])
            self.assertTrue(report["debug_snapshot_writes"])
            self.assertEqual(report["reads"], [])
            self.assertIn("error", report)


if __name__ == "__main__":
    unittest.main()
