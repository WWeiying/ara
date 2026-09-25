#!/usr/bin/env python3
"""Loopback protocol tests; they do not validate the FPGA receiver or DDR."""
from pathlib import Path
import json
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib

sys.dont_write_bytecode = True
SOFTWARE = Path(__file__).resolve().parents[2] / "ara_dsa_vcu118/software"
sys.path.insert(0, str(SOFTWARE))
import eth_load
from host_image import CAP_HOST, Image, Segment


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "payload.bin"
        self.source.write_bytes(bytes(range(256)) * 19)
        self.address = 0x80000000
        self.segment = Segment(self.address, 12000, self.source.stat().st_size,
                               str(self.source), 0, 5, "elf")
        self.image = Image(self.address, CAP_HOST, [self.segment], [])

    def test_blocks_include_zero_filled_bss_and_are_contiguous(self):
        blocks = list(eth_load.blocks(self.segment, 3000))
        self.assertEqual([len(data) for _, data in blocks], [3000] * 4)
        self.assertEqual([address for address, _ in blocks],
                         [self.address + i * 3000 for i in range(4)])
        self.assertEqual(b"".join(data for _, data in blocks),
                         self.source.read_bytes() + bytes(12000 - self.source.stat().st_size))

    def test_full_exchange_does_not_launch(self):
        client, server = socket.socketpair()
        self.addCleanup(client.close)
        self.addCleanup(server.close)
        received = bytearray()
        errors = []

        def peer():
            try:
                self.assertEqual(eth_load.receive_exact(server, len(eth_load.MAGIC)),
                                 eth_load.MAGIC)
                server.sendall(eth_load.HELLO.pack(eth_load.MAGIC, CAP_HOST, 3000))
                while True:
                    opcode, address, length, expected_crc = eth_load.RECORD.unpack(
                        eth_load.receive_exact(server, eth_load.RECORD.size))
                    data = eth_load.receive_exact(server, length)
                    self.assertEqual(zlib.crc32(data), expected_crc)
                    if opcode == b"DONE":
                        self.assertEqual((address, length), (self.address, 0))
                        break
                    self.assertEqual(opcode, b"DATA")
                    self.assertEqual(address, self.address + len(received))
                    received.extend(data)
                    server.sendall(eth_load.ACK.pack(address, expected_crc, 0))
                server.sendall(eth_load.ACK.pack(address, expected_crc, 0))
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=peer)
        worker.start()
        caps, chunk = eth_load.hello(client)
        self.assertEqual((caps, chunk), (CAP_HOST, 3000))
        result = eth_load.transfer(client, self.image, chunk)
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors, errors)
        self.assertEqual(result["payload_bytes"], 12000)
        self.assertEqual(result["verified_blocks"], 4)
        self.assertFalse(result["execution_started"])
        self.assertEqual(received, self.source.read_bytes() + bytes(12000 - self.source.stat().st_size))

    def test_rejects_wrong_crc_and_never_sends_done(self):
        client, server = socket.socketpair()
        self.addCleanup(client.close)
        self.addCleanup(server.close)
        seen = []

        def peer():
            header = eth_load.receive_exact(server, eth_load.RECORD.size)
            opcode, address, length, crc = eth_load.RECORD.unpack(header)
            seen.append(opcode)
            eth_load.receive_exact(server, length)
            server.sendall(eth_load.ACK.pack(address, crc ^ 1, 0))
            seen.append(server.recv(1))

        worker = threading.Thread(target=peer)
        worker.start()
        with self.assertRaisesRegex(RuntimeError, "DDR verification rejected"):
            eth_load.transfer(client, self.image, 3000)
        client.shutdown(socket.SHUT_WR)
        worker.join(timeout=5)
        self.assertEqual(seen, [b"DATA", b""])

    def test_rejects_bad_hello_and_short_reply(self):
        client, server = socket.socketpair()
        self.addCleanup(client.close)
        self.addCleanup(server.close)
        server.sendall(eth_load.HELLO.pack(b"BADMAGIC", CAP_HOST, 3000))
        with self.assertRaisesRegex(ValueError, "Incompatible"):
            eth_load.hello(client)
        client2, server2 = socket.socketpair()
        self.addCleanup(client2.close)
        server2.sendall(struct.pack("<I", 0))
        server2.close()
        with self.assertRaises(ConnectionError):
            eth_load.receive_exact(client2, eth_load.ACK.size)

    def test_existing_evidence_directory_is_not_overwritten(self):
        output = Path(self.temp.name) / "existing"
        output.mkdir()
        report = output / "report.json"
        report.write_text("original", encoding="ascii")
        self.assertEqual(eth_load.main(["--plan-only", "--elf", str(self.source),
                                        "--out", str(output)]), 1)
        self.assertEqual(report.read_text(encoding="ascii"), "original")

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_python_sender_matches_c_receiver(self):
        here = Path(__file__).resolve().parent
        source = here.parent / "ethernet/firmware/eth_loader_core.c"
        executable = Path(self.temp.name) / "eth_loader_pipe"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(source), str(here / "eth_loader_core_pipe.c"),
                        "-o", str(executable)], check=True)
        process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        self.addCleanup(process.stdout.close)

        class PipeStream:
            def sendall(self, data):
                process.stdin.write(data)
                process.stdin.flush()

            def recv(self, length):
                return process.stdout.read(length)

        caps, chunk = eth_load.hello(PipeStream())
        result = eth_load.transfer(PipeStream(), self.image, chunk)
        process.stdin.close()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual((caps, chunk), (CAP_HOST, 4096))
        self.assertEqual((result["payload_bytes"], result["verified_blocks"]), (12000, 3))

    def start_tcp_server(self, lwip=False):
        here = Path(__file__).resolve().parent
        firmware = here.parent / "ethernet/firmware"
        executable = Path(self.temp.name) / "eth_loader_tcp_server"
        command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror"]
        if lwip:
            command += ["-DETH_LOADER_LWIP", "-I", str(here / "include")]
        command += [str(firmware / "eth_loader_core.c"),
                    str(firmware / "eth_loader_tcp.c"),
                    str(here / "eth_loader_tcp_server.c"),
                    "-o", str(executable)]
        subprocess.run(command, check=True)
        process = subprocess.Popen([str(executable)], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        self.addCleanup(process.stdout.close)
        line = process.stdout.readline()
        self.assertTrue(line.startswith("PORT "), line)
        return process, int(line.split()[1])

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_real_tcp_sender_to_c_receiver_with_fragmented_hello(self):
        process, port = self.start_tcp_server()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as stream:
            stream.settimeout(5)
            for byte in eth_load.MAGIC:
                stream.sendall(bytes([byte]))
            self.assertEqual(eth_load.HELLO.unpack(
                eth_load.receive_exact(stream, eth_load.HELLO.size)),
                (eth_load.MAGIC, CAP_HOST, 4096))
            result = eth_load.transfer(stream, self.image, 4096)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(process.stdout.readline().strip(), "RESULT 0")
        self.assertEqual(result["payload_bytes"], 12000)
        self.assertEqual(result["verified_blocks"], 3)

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_lwip_socket_build_path_with_native_shim(self):
        process, port = self.start_tcp_server(lwip=True)
        with socket.create_connection(("127.0.0.1", port), timeout=5) as stream:
            self.assertEqual(eth_load.hello(stream), (CAP_HOST, 4096))
            result = eth_load.transfer(stream, self.image, 4096)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(process.stdout.readline().strip(), "RESULT 0")
        self.assertEqual(result["payload_bytes"], 12000)

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_real_tcp_rejects_corrupt_payload_before_write(self):
        process, port = self.start_tcp_server()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as stream:
            stream.settimeout(5)
            self.assertEqual(eth_load.hello(stream), (CAP_HOST, 4096))
            stream.sendall(eth_load.RECORD.pack(b"DATA", self.address, 4, 0))
            stream.sendall(b"bad!")
            address, crc, status = eth_load.ACK.unpack(
                eth_load.receive_exact(stream, eth_load.ACK.size))
            self.assertEqual((address, crc, status), (self.address, 0, 2))
        self.assertEqual(process.wait(timeout=5), 2)
        self.assertEqual(process.stdout.readline().strip(), "RESULT -9")

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_real_tcp_disconnection_aborts_transfer(self):
        process, port = self.start_tcp_server()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as stream:
            self.assertEqual(eth_load.hello(stream), (CAP_HOST, 4096))
            stream.sendall(eth_load.RECORD.pack(b"DATA", self.address, 4, 0))
            stream.sendall(b"ab")
        self.assertEqual(process.wait(timeout=5), 2)
        self.assertEqual(process.stdout.readline().strip(), "RESULT -8")

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_real_elf_cli_against_native_tcp_peer(self):
        elf = SOFTWARE / "host_smoke.elf"
        if not elf.is_file():
            self.skipTest("host_smoke.elf unavailable")
        process, port = self.start_tcp_server()
        output = Path(self.temp.name) / "report"
        self.assertEqual(eth_load.main(["--elf", str(elf), "--host", "127.0.0.1",
                                        "--port", str(port), "--out", str(output)]), 0)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(process.stdout.readline().strip(), "RESULT 0")
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["payload_bytes"], 4800)
        self.assertEqual(report["state"], "transfer_verified_by_peer_not_execution")
        self.assertFalse(report["board_verified"])


if __name__ == "__main__":
    unittest.main()
