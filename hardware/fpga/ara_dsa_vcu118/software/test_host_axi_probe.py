#!/usr/bin/env python3
"""Focused scratch probe tests; no Vivado or board required."""
import unittest

from host_image import CAP_HOST
from host_load import AXI_PREFLIGHT_ADDRESS, probe_axi_separated_burst, probe_axi_single_beat
from host_transport import Operation


class FakeTransport:
    def __init__(self, second_write="normal", burst_read="normal", burst_write="normal"):
        self.address = AXI_PREFLIGHT_ADDRESS
        self.memory = {self.address: bytes.fromhex("0123456789abcdef"),
                       self.address + 8: bytes.fromhex("1032547698badcfe")}
        self.memory.update({self.address + 8 * i: bytes([i]) * 8 for i in range(2, 10)})
        self.second_write = second_write
        self.burst_read = burst_read
        self.burst_write = burst_write
        self.operations = []

    def exchange(self, operations):
        replies = []
        for op in operations:
            self.operations.append(op)
            if op.kind == "READ":
                if op.beats == 2:
                    data = self.memory[op.address] + self.memory[op.address + 8]
                    replies.append(data if self.burst_read == "normal" else data[:8] * 2)
                else:
                    replies.append(self.memory[op.address])
            elif op.beats == 2:
                self.memory[op.address] = op.data[:8]
                if self.burst_write == "normal":
                    self.memory[op.address + 8] = op.data[8:]
                replies.append(b"")
            elif op.address == self.address + 8 and self.second_write == "alias":
                self.memory[self.address] = op.data
                replies.append(b"")
            elif op.address == self.address + 8 and self.second_write == "ignored":
                replies.append(b"")
            else:
                self.memory[op.address] = op.data
                replies.append(b"")
        return replies


class HostAxiProbeTests(unittest.TestCase):
    def test_single_beat_at_second_address_and_restore(self):
        transport = FakeTransport()
        original = transport.memory.copy()
        record = {}
        probe_axi_single_beat(transport, CAP_HOST, record)
        self.assertTrue(record["verified"])
        self.assertTrue(record["restored"])
        self.assertEqual(transport.memory, original)
        self.assertEqual(record["observed_bytes_at_each_address"],
                         [original[transport.address].hex(), record["written_bytes_at_target"]])

    def test_alias_detected_and_both_words_restored(self):
        transport = FakeTransport("alias")
        original = transport.memory.copy()
        record = {}
        with self.assertRaisesRegex(RuntimeError, "single-beat write/read"):
            probe_axi_single_beat(transport, CAP_HOST, record)
        self.assertFalse(record["verified"])
        self.assertTrue(record["restored"])
        self.assertEqual(transport.memory, original)

    def test_ignored_write_detected(self):
        transport = FakeTransport("ignored")
        original = transport.memory.copy()
        record = {}
        with self.assertRaisesRegex(RuntimeError, "single-beat write/read"):
            probe_axi_single_beat(transport, CAP_HOST, record)
        self.assertTrue(record["restored"])
        self.assertEqual(transport.memory, original)

    def test_separated_burst_and_restore(self):
        transport = FakeTransport()
        original = transport.memory.copy()
        record = {}
        probe_axi_separated_burst(transport, CAP_HOST, record)
        self.assertTrue(record["burst_read_verified"])
        self.assertTrue(record["write_attempted"])
        self.assertTrue(record["separated_write_verified"])
        self.assertTrue(record["restored"])
        self.assertEqual(transport.memory, original)

    def test_failed_second_burst_beat_is_detected_and_restored(self):
        transport = FakeTransport(burst_write="first_only")
        original = transport.memory.copy()
        record = {}
        with self.assertRaisesRegex(RuntimeError, "did not update both"):
            probe_axi_separated_burst(transport, CAP_HOST, record)
        self.assertTrue(record["burst_read_verified"])
        self.assertFalse(record["separated_write_verified"])
        self.assertTrue(record["restored"])
        self.assertEqual(transport.memory, original)

    def test_bad_burst_read_stops_before_write(self):
        transport = FakeTransport(burst_read="bad")
        original = transport.memory.copy()
        record = {}
        with self.assertRaisesRegex(RuntimeError, "two-beat read differs"):
            probe_axi_separated_burst(transport, CAP_HOST, record)
        self.assertFalse(record["burst_read_verified"])
        self.assertFalse(record["write_attempted"])
        self.assertTrue(record["restored"])
        self.assertEqual(len(record["neighbor_single_bytes"]), 10)
        self.assertEqual(record["post_single_bytes"], record["original_bytes_at_each_address"])
        self.assertTrue(all(op.kind == "READ" for op in transport.operations))
        self.assertEqual(transport.memory, original)

    def test_word_separators_only_on_explicit_multibeat_write(self):
        low = bytes.fromhex("0011223344556677")
        high = bytes.fromhex("8899aabbccddeeff")
        wire = Operation("M", "WRITE", AXI_PREFLIGHT_ADDRESS, 2, low + high,
                         separate_words=True).wire()
        self.assertEqual(wire.split()[-1], "ffeeddccbbaa9988_7766554433221100")
        with self.assertRaisesRegex(ValueError, "Word separators"):
            Operation("M", "READ", AXI_PREFLIGHT_ADDRESS, 2, separate_words=True).wire()


if __name__ == "__main__":
    unittest.main()
