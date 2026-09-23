#!/usr/bin/env python3
"""Focused scratch probe tests; no Vivado or board required."""
import unittest

from host_image import CAP_HOST
from host_load import AXI_PREFLIGHT_ADDRESS, probe_axi_single_beat


class FakeTransport:
    def __init__(self, second_write="normal"):
        self.address = AXI_PREFLIGHT_ADDRESS
        self.memory = {self.address: bytes.fromhex("0123456789abcdef"),
                       self.address + 8: bytes.fromhex("1032547698badcfe")}
        self.second_write = second_write

    def exchange(self, operations):
        replies = []
        for op in operations:
            if op.kind == "READ":
                replies.append(self.memory[op.address])
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


if __name__ == "__main__":
    unittest.main()
