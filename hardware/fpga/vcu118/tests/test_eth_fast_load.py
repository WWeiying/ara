import socket
import sys
import itertools
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ara_dsa_vcu118" / "software"))
import eth_fast_load as loader


class Peer:
    def __init__(self, corrupt=False):
        self.queue = []
        self.dropped_one = False
        self.sent = []
        self.corrupt = corrupt

    def settimeout(self, value):
        self.timeout = value

    def send(self, packet):
        self.sent.append(packet)
        magic, session, opcode, status, arg0, arg1 = loader.HEADER.unpack_from(packet)
        assert magic == loader.MAGIC and status == 0
        if opcode == loader.DATA and arg0 == 1 and not self.dropped_one:
            self.dropped_one = True
            return len(packet)
        reply = (loader.HEADER.pack(
            magic, session, opcode | loader.REPLY, 0, arg0, arg1) +
            packet[loader.HEADER.size:])
        if self.corrupt and opcode == loader.DATA:
            reply = reply[:-1] + bytes([reply[-1] ^ 1])
        self.queue.append(reply)
        return len(packet)

    def recv(self, size):
        if self.queue:
            return self.queue.pop(0)
        raise socket.timeout()


class FastLoadTests(unittest.TestCase):
    def test_lost_early_packet_cannot_overrun_board_window(self):
        class BoundedPeer(Peer):
            def __init__(self):
                super().__init__()
                self.base = 0
                self.received = set()

            def send(self, packet):
                magic, session, opcode, _, sequence, size = loader.HEADER.unpack_from(packet)
                if opcode == loader.DATA:
                    if sequence >= self.base + 64:
                        self.queue.append(loader.HEADER.pack(
                            magic, session, opcode | loader.REPLY, 3, sequence, size))
                        return len(packet)
                    if sequence != 1 or self.dropped_one:
                        self.received.add(sequence)
                        while self.base in self.received:
                            self.received.remove(self.base)
                            self.base += 1
                return super().send(packet)

        address = 0x81000000
        size = 80 * loader.CHUNK
        data = bytes(i & 255 for i in range(size))
        segment = SimpleNamespace(address=address, size=size,
                                  chunks=lambda: iter(((address, data),)))
        ticks = itertools.count()
        with patch.object(loader.time, "monotonic", side_effect=lambda: next(ticks) * 0.001):
            result = loader.transfer_segment(BoundedPeer(), segment, 99, 8, 3, 1.0)
        self.assertEqual(result["packets"], 80)
        self.assertEqual(result["data_retries"], 1)

    def test_preflight_rejects_reserved_ddr_before_transfer(self):
        good = SimpleNamespace(address=loader.DDR_START, size=8)
        reserved = SimpleNamespace(address=loader.DDR_LIMIT - 4, size=8)
        with self.assertRaisesRegex(ValueError, "Outside Ethernet loader DDR range"):
            loader.validate_segments((good, reserved))
        loader.validate_segments((good,))

    def test_three_packets_with_retry(self):
        size = 2 * loader.CHUNK + 7
        address = 0x81000FF8
        data = bytes(i & 255 for i in range(size))
        segment = SimpleNamespace(
            address=address, size=size,
            chunks=lambda: iter(((address, data[:1500]),
                                 (address + 1500, data[1500:]))))
        peer = Peer()
        result = loader.transfer_segment(peer, segment, 1234, 2, 3, 0.0001)
        self.assertEqual(result["packets"], 3)
        self.assertEqual(result["data_retries"], 1)
        self.assertEqual([loader.HEADER.unpack_from(p)[2] for p in peer.sent],
                         [loader.BEGIN, loader.DATA, loader.DATA, loader.DATA,
                          loader.DATA, loader.END])

    def test_rejection(self):
        reply = loader.HEADER.pack(loader.MAGIC, 9, loader.DATA | loader.REPLY,
                                   1, 0, 10)
        with self.assertRaisesRegex(RuntimeError, "status=1"):
            loader.unpack_reply(reply, 9, loader.DATA)
        self.assertIsNone(loader.unpack_reply(reply, 10, loader.DATA))

    def test_corrupt_ddr_readback_fails(self):
        address = 0x81000000
        segment = SimpleNamespace(address=address, size=3,
                                  chunks=lambda: iter(((address, b"abc"),)))
        with self.assertRaisesRegex(ValueError, "DDR readback mismatch"):
            loader.transfer_segment(Peer(corrupt=True), segment, 5, 1, 0, 0.001)


if __name__ == "__main__":
    unittest.main()
