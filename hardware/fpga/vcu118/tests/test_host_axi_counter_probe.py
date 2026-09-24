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
            valid_address = (op.address == probe.ADDRESSES[op.burst] if op.beats == 2 else
                             any(base <= op.address < base + 160
                                 for base in probe.ADDRESSES.values()))
            if op.bus != "M" or op.kind != "READ" or not valid_address:
                raise AssertionError("Only the selected memory address may be read")
            op.wire()
        return [bytes(op.beats * 8) for op in operations]


class ProbeTests(unittest.TestCase):
    @staticmethod
    def debug_state(frozen=0):
        state = {probe.COMMAND: frozen, probe.STATUS: 7, probe.WATCHDOG: 0}

        def read(_, addresses):
            return [state[address] for address in addresses]

        def write(_, values):
            for address, value in values:
                if address == probe.COMMAND:
                    state[address] = 0 if value == probe.RESUME else 1

        return state, read, write

    def test_counter_deltas_and_order(self):
        memory = Memory()
        report = {"reads": []}
        _, read, write = self.debug_state()
        with patch.object(probe, "identity", return_value={"caps": 1}), \
             patch.object(probe, "read_debug", side_effect=read), \
             patch.object(probe, "write_debug", side_effect=write), \
             patch.object(probe, "capture_snapshot",
                          side_effect=[snap(1, 10, 80), snap(2, 10, 80),
                                       snap(3, 11, 96), snap(4, 12, 112)]):
            probe.collect(memory, report)
        self.assertEqual([op.burst for op in memory.calls if op.beats == 2],
                         ["FIXED", "INCR"])
        self.assertEqual(report["idle_ar_delta"], 0)
        self.assertEqual([row["delta"] for row in report["reads"]],
                         [{"ar_count": 1, "r_bytes": 16, "error_count": 0}] * 2)
        self.assertTrue(all(row["neighbor_stable"] for row in report["reads"]))

    def test_idle_activity_blocks_probe(self):
        memory = Memory()
        _, read, write = self.debug_state()
        with patch.object(probe, "identity", return_value={"caps": 1}), \
             patch.object(probe, "read_debug", side_effect=read), \
             patch.object(probe, "write_debug", side_effect=write), \
             patch.object(probe, "capture_snapshot",
                          side_effect=[snap(1, 10, 80), snap(2, 11, 88)]):
            with self.assertRaisesRegex(RuntimeError, "changed while idle"):
                probe.collect(memory, {"reads": []})
        self.assertEqual(memory.calls, [])

    def test_frozen_counters_require_opt_in_and_are_restored(self):
        memory = Memory()
        state, read, write = self.debug_state(frozen=1)
        with patch.object(probe, "identity", return_value={"caps": 1}), \
             patch.object(probe, "read_debug", side_effect=read), \
             patch.object(probe, "write_debug", side_effect=write), \
             patch.object(probe, "capture_snapshot",
                          side_effect=[snap(1, 10, 80), snap(2, 10, 80),
                                       snap(3, 11, 96), snap(4, 12, 112)]):
            with self.assertRaisesRegex(RuntimeError, "frozen"):
                probe.collect(memory, {"reads": []})
            self.assertEqual(memory.calls, [])
            report = {"reads": []}
            probe.collect(memory, report, resume_counters=True)
        self.assertEqual(state[probe.COMMAND], 1)
        self.assertTrue(report["restored_frozen"])
        self.assertEqual(len(report["reads"]), 2)

    def test_frozen_state_is_restored_when_idle_check_fails(self):
        memory = Memory()
        state, read, write = self.debug_state(frozen=1)
        report = {"reads": []}
        with patch.object(probe, "identity", return_value={"caps": 1}), \
             patch.object(probe, "read_debug", side_effect=read), \
             patch.object(probe, "write_debug", side_effect=write), \
             patch.object(probe, "capture_snapshot",
                          side_effect=[snap(1, 10, 80), snap(2, 11, 88)]):
            with self.assertRaisesRegex(RuntimeError, "changed while idle"):
                probe.collect(memory, report, resume_counters=True)
        self.assertEqual(state[probe.COMMAND], 1)
        self.assertTrue(report["restored_frozen"])
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
