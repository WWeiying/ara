#!/usr/bin/env python3
"""Host image/ABI tests and real Tcl transport tests with mocked Vivado hardware."""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, call, patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SOFTWARE = HERE.parent / "software"
ROOT = HERE.parents[3]
EXPORTED = HERE.parent.parent / "ara_dsa_vcu118/software"
sys.path.insert(0, str(SOFTWARE))
import host_image as image
import host_load as host
import host_ddr_test as ddr_test
import host_transport as transport_module
from host_transport import Operation, TransportError, VivadoTransport


def make_elf(path, segments=None, entry=0x80000000, elf_type=2, endian=1):
    segments = segments or [(0x80000000, b"\x13\x00\x00\x00abcd", 32, 5)]
    ident = b"\x7fELF" + bytes([2, endian, 1]) + bytes(9)
    data = bytearray(ident + struct.pack("<HHIQQQIHHHHHH", elf_type, 243, 1, entry,
                                       64, 0, 0, 64, 56, len(segments), 0, 0, 0))
    offset = 64 + 56 * len(segments)
    for address, payload, size, flags in segments:
        data.extend(struct.pack("<IIQQQQQQ", 1, flags, offset, address, address,
                                len(payload), size, 1))
        offset += len(payload)
    for _, payload, _, _ in segments:
        data.extend(payload)
    path.write_bytes(data)
    return path


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.elf = make_elf(self.base / "test.elf")

    def test_endian_known_vector(self):
        data = bytes(range(16))
        self.assertEqual(image.to_axi_hex(data), "0f0e0d0c0b0a09080706050403020100")
        self.assertEqual(image.from_axi_hex("0f0e0d0c0b0a0908_0706050403020100", 16), data)
        self.assertEqual(image.to_axi_hex(b"\x02\x00\x00\x00", 4), "00000002")
        for bad in ("00", "0" * 31, "x" * 32):
            with self.assertRaises(ValueError):
                image.from_axi_hex(bad, 16)

    def test_ranges_and_caps(self):
        image.check_range(0x80000000, 8, 1)
        image.check_range(0xFFFFFFF8, 8, 1)
        image.check_range(0x100000000, 8, 3)
        image.check_range(0x17FFFFFF8, 8, 3)
        for address, size, caps in ((0x80000000, 1, 0), (0x100000000, 8, 1),
                                    (0xFFFFFFF8, 16, 3), (0x17FFFFFF8, 16, 3),
                                    (0x03010000, 8, 3), (-8, 8, 3), (0x80000000, 0, 3)):
            with self.subTest(address=address, size=size, caps=caps), self.assertRaises(ValueError):
                image.check_range(address, size, caps)

    def test_bss_zero_filled_and_hashed(self):
        prepared = image.prepare_image(self.elf)
        segment = prepared.segments[0]
        actual = b"".join(data for _, data in segment.chunks())
        self.assertEqual(actual, b"\x13\x00\x00\x00abcd" + bytes(24))
        self.assertEqual(segment.sha256, __import__("hashlib").sha256(actual).hexdigest())
        self.assertEqual(prepared.sources[0]["sha256"], image.sha256_file(self.elf))

    def test_large_bss_is_streamed(self):
        make_elf(self.elf, [(0x80000000, b"\x13\x00", 1024 * 1024, 5)])
        prepared = image.prepare_image(self.elf)
        self.assertLessEqual(max(len(x) for _, x in prepared.segments[0].chunks()), 2048)

    def test_raw_overlap_includes_bss(self):
        raw = self.base / "raw.bin"
        raw.write_bytes(b"xyz")
        with self.assertRaisesRegex(ValueError, "overlap"):
            image.prepare_image(self.elf, [(0x80000010, raw)])
        prepared = image.prepare_image(self.elf, [(0x100000000, raw)], caps=3)
        self.assertEqual(prepared.segments[1].kind, "raw")
        with self.assertRaises(ValueError):
            image.prepare_image(self.elf, [(0x100000000, raw)], caps=1)

    def test_enabled_bank_elf_edges(self):
        for start, end, caps in ((image.DDR1[0], image.DDR1[1], 1),
                                 (image.DDR2[0], image.DDR2[1], 3)):
            for address in (start, end - 8):
                make_elf(self.elf, [(address, bytes(range(8)), 8, 5)], entry=address)
                self.assertEqual(image.prepare_image(self.elf, caps=caps).entry, address)
            make_elf(self.elf, [(end - 8, bytes(range(8)), 16, 5)], entry=end - 8)
            with self.assertRaises(ValueError):
                image.prepare_image(self.elf, caps=caps)

    def test_ddr_plan_and_destructive_gate(self):
        self.assertEqual([r["address"] for r in ddr_test.plan(3)], [0xFFFF0000, 0x17FFF0000])
        self.assertEqual(len(ddr_test.plan(1)), 1)
        with self.assertRaises(ValueError):
            ddr_test.test_memory(None, 3)
        with self.assertRaises(ValueError):
            ddr_test.test_memory(None, 3, True, False)

    def test_invalid_elf(self):
        for entry, size, flags, elf_type in ((0x80000001, 32, 5, 2), (0x80000010, 32, 5, 2),
                                           (0x80000000, 32, 4, 2), (0x80000000, 1, 5, 2),
                                           (0x80000000, 32, 5, 3)):
            make_elf(self.elf, [(0x80000000, b"\x13\x00\x00\x00", size, flags)], entry, elf_type)
            with self.subTest(entry=entry, size=size, flags=flags, elf_type=elf_type):
                with self.assertRaises(ValueError):
                    image.prepare_image(self.elf)
        make_elf(self.elf)
        self.elf.write_bytes(self.elf.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "truncated"):
            image.prepare_image(self.elf)

    def test_linux_opensbi_dynamic_header_is_explicitly_scoped(self):
        artifacts = EXPORTED.parent / "linux/artifacts"
        firmware = artifacts / "fw_jump.elf"
        with self.assertRaisesRegex(ValueError, "Dynamic ELF"):
            image.prepare_image(firmware)
        prepared = image.prepare_image(firmware, [
            (0x80100000, artifacts / "ara_vcu118.dtb"),
            (0x80200000, artifacts / "Image"),
            (0x88000000, artifacts / "initramfs.cpio")], allow_dynamic=True)
        self.assertEqual(prepared.entry, 0x80000000)
        self.assertEqual(sum(segment.size for segment in prepared.segments), 30029946)
        self.assertEqual(len(prepared.segments), 5)

    def test_linux_console_marker_requires_actual_uart_bytes(self):
        class FakePort:
            def __init__(self, parts):
                self.parts = list(parts)
                self.launched = False

            def read(self, size):
                if self.launched and self.parts:
                    return self.parts.pop(0)
                time.sleep(0.005)
                return b""

        port = FakePort([b"OpenSBI\r\nLinux console, DDR and ",
                         b"RVV handoff are alive\r\n"])
        result = host.wait_linux_console(port, self.base, lambda: setattr(port, "launched", True), 1)
        self.assertTrue(result["marker_seen"])
        self.assertIn("OpenSBI", (self.base / "uart.txt").read_text())
        missing = self.base / "missing"
        missing.mkdir()
        with self.assertRaisesRegex(RuntimeError, "marker not seen"):
            host.wait_linux_console(FakePort([]), missing, lambda: None, 0.03)
        self.assertFalse(json.loads((missing / "uart.json").read_text())["marker_seen"])

    def test_burst_bounds_every_alignment(self):
        for low in (0, 1, 7, 2040, 2047, 4088, 4095):
            start = 0x80000000 + low
            slices = list(image.burst_slices(start, 12000))
            self.assertEqual(sum(length for _, _, length in slices), 12000)
            for address, offset, length in slices:
                aligned = address & ~7
                enclosed = (address - aligned + length + 7) & ~7
                self.assertEqual(address, start + offset)
                self.assertLessEqual(enclosed, 256 * 8)
                self.assertLessEqual((aligned & 4095) + enclosed, 4096)

    def test_operation_rejects_narrow_and_bad_burst(self):
        for op in (Operation("M", "READ", 0x80000004), Operation("D", "READ", 0, 2),
                   Operation("M", "READ", 0x80000FF8, 2), Operation("M", "READ", 0, 257),
                   Operation("M", "WRITE", 0, data=b"abcd")):
            with self.assertRaises(ValueError):
                op.wire()

    def test_fixed_read_is_diagnostic_only(self):
        self.assertEqual(Operation("M", "READ", 0xffff0000, 2, burst="FIXED").wire(),
                         "M READ 00000000ffff0000 2 - FIXED")
        self.assertEqual(Operation("M", "READ", 0xffff0000, 2).wire(),
                         "M READ 00000000ffff0000 2 -")
        for op in (Operation("M", "WRITE", 0, data=b"12345678", burst="FIXED"),
                   Operation("D", "READ", 0, burst="FIXED"),
                   Operation("M", "READ", 0, burst="WRAP")):
            with self.assertRaises(ValueError):
                op.wire()

    def test_modifiable_cache_is_diagnostic_only(self):
        self.assertEqual(Operation("M", "READ", 0xa1011000, 2, cache=2).wire(),
                         "M READ 00000000a1011000 2 - INCR 2")
        for op in (Operation("M", "READ", 0, cache=1),
                   Operation("M", "WRITE", 0, data=b"12345678", cache=2),
                   Operation("D", "READ", 0, cache=2)):
            with self.assertRaises(ValueError):
                op.wire()

    def test_requires_reset_before_any_transport(self):
        with self.assertRaisesRegex(ValueError, "full-reset-confirmed"):
            host.load_and_run(None, None, self.base, {})

    def test_parse_windows_raw_path(self):
        address, path = host.parse_load("0x100000000:D:\\models\\test.bin")
        self.assertEqual(address, 0x100000000)
        self.assertEqual(str(path), "D:\\models\\test.bin")


class MeasurementTests(unittest.TestCase):
    def test_only_verified_load_is_timed_and_bss_counts_once(self):
        prepared = Mock(segments=[Mock(size=32, file_size=8), Mock(size=16, file_size=16)])
        records = [{"verified": True}]
        report = {}
        events = []

        def clock():
            events.append("clock")
            return 100 if len(events) == 1 else 102

        def load(*args, **kwargs):
            events.append("verified_load")
            return records

        with patch.object(host.time, "monotonic", side_effect=clock), \
                patch.object(host, "verified_load", side_effect=load) as mocked_load:
            self.assertEqual(host.measured_verified_load(None, prepared, report, 7), records)
        mocked_load.assert_called_once_with(None, prepared, 7, single_beat=False)
        self.assertEqual(events, ["clock", "verified_load", "clock"])
        metrics = report["load_metrics"]
        self.assertTrue(metrics["complete"])
        self.assertEqual(metrics["elapsed_seconds"], 2)
        self.assertEqual(metrics["payload_bytes_including_bss"], 48)
        self.assertEqual(metrics["payload_bytes_per_second_including_readback"], 24)
        self.assertEqual(metrics["ratio_to_uart_theoretical_not_measured_speedup"], 24 / 11520)
        self.assertIn("NOT measured speedup", metrics["comparison"])

    def test_failed_or_zero_duration_load_never_claims_throughput(self):
        for failure in (None, RuntimeError("bad readback")):
            report = {}
            prepared = Mock(segments=[Mock(size=32)])
            with patch.object(host.time, "monotonic", side_effect=[10, 10]), \
                    patch.object(host, "verified_load", side_effect=failure, return_value=[]):
                if failure:
                    with self.assertRaisesRegex(RuntimeError, "bad readback"):
                        host.measured_verified_load(None, prepared, report)
                else:
                    host.measured_verified_load(None, prepared, report)
            self.assertEqual(report["load_metrics"]["complete"], failure is None)
            self.assertIsNone(report["load_metrics"]["payload_bytes_per_second_including_readback"])

    def test_software_measurement_command_order(self):
        header = (SOFTWARE / "fpga_debug.h").read_text()
        begin = header.split("static inline void fpga_debug_begin(void) {", 1)[1].split("}", 1)[0]
        self.assertEqual(begin.split(),
                         "fpga_debug_write(FPGA_DEBUG_COMMAND, FPGA_DEBUG_CLEAR); fpga_debug_fence();".split())
        finish = header.split("static inline void fpga_debug_finish(uint32_t result) {", 1)[1].split("}", 1)[0]
        self.assertEqual(finish.split(), """
            fpga_debug_fence();
            fpga_debug_write(FPGA_DEBUG_COMMAND, FPGA_DEBUG_FREEZE);
            fpga_debug_fence();
            fpga_debug_write(FPGA_DEBUG_COMMAND, FPGA_DEBUG_SNAPSHOT);
            fpga_debug_write(FPGA_DEBUG_RESULT, result);
            fpga_debug_write(FPGA_DEBUG_WATCHDOG, 0);
            fpga_debug_fence();
            fpga_debug_write(FPGA_DEBUG_DONE, 1u);
            fpga_debug_fence();
        """.split())
        smoke = (SOFTWARE / "host_smoke.c").read_text()
        self.assertLess(smoke.index("fpga_debug_present()"), smoke.index("fpga_debug_begin();"))
        self.assertLess(smoke.index("fpga_debug_begin();"), smoke.index("#ifdef HOST_DDR2_CANARY"))


class ProcessCleanupTests(unittest.TestCase):
    def test_vivado_path_lookup_resolves_windows_batch_launcher(self):
        launcher = r"C:\Program Files\Xilinx\Vivado\2020.1\bin\vivado.bat"
        with patch.object(transport_module.shutil, "which", return_value=launcher) as which:
            transport = VivadoTransport("unused")
        which.assert_called_once_with("vivado")
        self.assertEqual(transport.command[:3], [launcher, "-mode", "batch"])

    def test_explicit_vivado_path_and_injected_command_are_preserved(self):
        launcher = r"D:\Xilinx\Vivado\2020.1\bin\vivado.bat"
        for resolved in (launcher, None):
            with self.subTest(resolved=resolved), \
                    patch.object(transport_module.shutil, "which", return_value=resolved) as which:
                transport = VivadoTransport("unused", vivado=launcher)
            which.assert_called_once_with(launcher)
            self.assertEqual(transport.command[0], launcher)
        command = ["tclsh", "mock.tcl"]
        with patch.object(transport_module.shutil, "which") as which:
            self.assertEqual(VivadoTransport("unused", command=command).command, command)
        which.assert_not_called()

    def test_windows_cleanup_plan_targets_owned_pid_tree_only(self):
        self.assertEqual(transport_module.windows_tree_command(1234),
                         ["taskkill", "/PID", "1234", "/T", "/F"])
        for bad in (0, -1, "vivado.exe"):
            with self.assertRaises(ValueError):
                transport_module.windows_tree_command(bad)
        process = Mock(pid=1234, returncode=1)
        with patch.object(transport_module.subprocess, "run", return_value=Mock(returncode=0)) as run:
            transport_module.stop_owned_tree(process, "nt")
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "1234", "/T", "/F"])
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_windows_cleanup_failure_is_not_hidden(self):
        with patch.object(transport_module.subprocess, "run",
                          return_value=Mock(returncode=1, stdout=b"denied")):
            with self.assertRaisesRegex(TransportError, "tree cleanup failed"):
                transport_module.stop_owned_tree(Mock(pid=1234), "nt")

    def test_posix_cleanup_targets_dedicated_group_even_after_leader_exits(self):
        self.assertEqual(transport_module.process_start_options("posix"), {"start_new_session": True})
        self.assertEqual(transport_module.process_start_options("nt"), {})
        process = Mock(pid=1234)
        with patch.object(transport_module.os, "killpg", create=True) as killpg:
            transport_module.stop_owned_tree(process, "posix")
        self.assertEqual(killpg.call_args_list, [call(1234, transport_module.signal.SIGTERM),
                                               call(1234, transport_module.signal.SIGKILL)])
        process.terminate.assert_not_called()

    def test_close_waits_for_graceful_quit_before_tree_cleanup(self):
        transport = VivadoTransport("unused")
        sock, process = Mock(), Mock(pid=1234)
        transport.sock, transport.process = sock, process
        process.wait.side_effect = subprocess.TimeoutExpired("vivado.bat", 2)
        events = []
        sock.sendall.side_effect = lambda _: events.append("quit")
        process.wait.side_effect = lambda **_: (events.append("wait"),
                                              (_ for _ in ()).throw(subprocess.TimeoutExpired("owned", 2)))[1]
        with patch.object(transport_module, "stop_owned_tree",
                          side_effect=lambda _: events.append("tree")) as stop:
            transport.close()
        self.assertEqual(events, ["quit", "wait", "tree"])
        stop.assert_called_once_with(process)
        self.assertIsNone(transport.process)


@unittest.skipUnless(shutil.which("tclsh"), "tclsh is required for mocked Vivado tests")
class TclTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.elf = make_elf(self.base / "test.elf")

    def transport(self, mode="pass", name="session", timeout=2):
        return VivadoTransport(self.base / name, timeout=timeout, startup_timeout=2,
                               mem_cell="gen_host.i_host_bridge.i_jtag_mem",
                               debug_cell="gen_host.i_host_bridge.i_jtag_debug",
                               command=[shutil.which("tclsh"), str(HERE / "test_host_mock.tcl"),
                                        mode, str(SOFTWARE / "host_vivado.tcl")])

    def run_image(self, transport, seconds=0.02):
        prepared = image.prepare_image(self.elf, caps=3)
        report = {"passed": False}
        host.load_and_run(transport, prepared, self.base, report, True, 0x12345678, seconds)
        return report

    def test_actual_success_and_snapshot_artifacts(self):
        with self.transport() as transport:
            report = self.run_image(transport)
            self.assertTrue(report["passed"])
            self.assertEqual(report["state"], "passed")
            readback = transport.exchange([Operation("M", "READ", 0x80000000, 4)])[0]
            self.assertEqual(readback, b"\x13\x00\x00\x00abcd" + bytes(24))
            self.assertEqual(report["readback"][0]["readback_sha256"],
                             image.prepare_image(self.elf).segments[0].sha256)
            self.assertEqual(report["load_metrics"]["payload_bytes_including_bss"], 32)
            self.assertGreater(report["load_metrics"]["elapsed_seconds"], 0)
            self.assertIn("boot_control_and_launch", report["other_timings_seconds"])
            self.assertIn("result_snapshot_collection", report["other_timings_seconds"])
            self.assertIn("axi_mapping_preflight", report["other_timings_seconds"])
            self.assertTrue(report["axi_mapping_preflight"]["verified"])
            self.assertTrue(report["axi_mapping_preflight"]["restored"])
        snapshot = json.loads((self.base / "snapshot.json").read_text())
        self.assertEqual(snapshot["live"]["run_id"], 0x12345678)
        self.assertEqual(snapshot["core"]["retired"], 123)
        self.assertEqual(snapshot["ddr1"]["read_outstanding"], 2)
        self.assertIn("ddr1.r_bytes", (self.base / "snapshot.csv").read_text())

    def test_linux_launch_only_does_not_wait_for_debug_done_or_freeze_running_core(self):
        with self.transport() as transport:
            report = {"passed": False}
            host.load_and_run(transport, image.prepare_image(self.elf, caps=3), self.base,
                              report, True, 17, 0.01, 0, 16, launch_only=True)
            self.assertEqual(report["state"], "running")
            self.assertFalse(report["passed"])
            self.assertTrue((self.base / "load_snapshot.json").is_file())
            self.assertFalse((self.base / "snapshot.json").exists())

    def test_fixed_burst_reaches_tcl_and_repeats_one_address(self):
        with self.transport() as transport:
            address = 0xffff0000
            single = transport.exchange([Operation("M", "READ", address)])[0]
            fixed = transport.exchange(
                [Operation("M", "READ", address, 3, burst="FIXED")])[0]
            self.assertEqual(fixed, single * 3)
            self.assertEqual(len(transport.exchange(
                [Operation("M", "READ", address, 3)])[0]), 24)

    def test_cache_probe_reaches_tcl_without_changing_default(self):
        with self.transport() as transport:
            default, modified = transport.exchange([
                Operation("M", "READ", 0xa1011000, 2),
                Operation("M", "READ", 0xa1011000, 2, cache=2),
            ])
            self.assertEqual(default, modified)
        audit = (self.base / "session" / "transport.jsonl").read_text()
        operations = json.loads(audit.splitlines()[0])["operations"]
        self.assertNotIn("cache", operations[0])
        self.assertEqual(operations[1]["cache"], 2)

    def test_single_beat_load_works_when_bursts_are_broken(self):
        prepared = image.prepare_image(self.elf, caps=3)
        report = {"passed": False}
        with self.transport("burst_left") as transport:
            host.load_and_run(transport, prepared, self.base, report, True,
                              0x12345678, 0.02, batch_chunks=2, single_beat=True)
        self.assertTrue(report["passed"])
        self.assertEqual(report["memory_transaction_mode"], "single_beat")
        self.assertTrue(report["axi_single_beat_preflight"]["verified"])
        self.assertTrue(report["axi_single_beat_preflight"]["restored"])
        self.assertEqual(report["readback"][0]["readback_sha256"], prepared.segments[0].sha256)
        entries = [json.loads(line) for line in
                   (self.base / "session/transport.jsonl").read_text().splitlines()]
        memory_ops = [op for entry in entries for op in entry.get("operations", [])
                      if op["bus"] == "M"]
        self.assertTrue(memory_ops)
        self.assertTrue(all(op["beats"] == 1 for op in memory_ops))

    def test_batched_replies_arrive_before_entire_batch_finishes(self):
        with self.transport("slow_mem", timeout=1) as transport:
            replies = transport.exchange([Operation("M", "READ", 0xffff0000 + 8 * i)
                                          for i in range(3)])
        self.assertEqual(len(replies), 3)

    def test_single_beat_payload_corruption_prevents_launch(self):
        prepared = image.prepare_image(self.elf, caps=3)
        report = {"passed": False}
        with self.transport("payload_corrupt") as transport:
            with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
                host.load_and_run(transport, prepared, self.base, report, True,
                                  0x12345678, 0.02, single_beat=True)
            self.assertEqual(host.read_debug(transport, [host.DONE]), [0])
        self.assertFalse(report["passed"])
        self.assertTrue(report["axi_single_beat_preflight"]["verified"])
        self.assertFalse(report["load_metrics"]["complete"])

    def test_preflight_uses_individual_addresses_and_restores_scratch(self):
        address = host.AXI_PREFLIGHT_ADDRESS
        locations = [address - 8, address, address + 8, address + 16]
        original = [bytes.fromhex(word) for word in
                    ("aabbccdd11223344", "deadbeef13579bdf", "f0e1d2c34b5a6978", "123456789abcdef0")]
        record = {}
        with self.transport() as transport:
            transport.exchange([Operation("M", "WRITE", a, data=value)
                                for a, value in zip(locations, original)])
            host.preflight_axi_mapping(transport, 3, record)
            restored = transport.exchange([Operation("M", "READ", a) for a in locations])
        self.assertEqual(restored, original)
        self.assertTrue(record["verified"])
        self.assertTrue(record["restored"])
        self.assertEqual(record["observed_bytes_at_each_address"],
                         ["0123456789abcdef", "1032547698badcfe"])
        entries = [json.loads(line) for line in (self.base / "session/transport.jsonl").read_text().splitlines()]
        operations = [op for entry in entries for op in entry.get("operations", [])]
        burst_index = next(i for i, op in enumerate(operations) if op["kind"] == "WRITE" and op["beats"] == 2)
        self.assertEqual(operations[burst_index + 1:burst_index + 3],
                         [{"bus": "M", "kind": "READ", "address": a, "beats": 1}
                          for a in (address, address + 8)])

    def test_mirrored_burst_readback_can_pass_but_preflight_rejects(self):
        record = {}
        prepared = image.prepare_image(self.elf, caps=3)
        with self.transport("burst_left") as transport:
            # Both directions use the opposite convention: round-trip hash alone
            # passes even though the first instruction is at the wrong address.
            records = host.verified_load(transport, prepared)
            self.assertTrue(records[0]["verified"])
            first = transport.exchange([Operation("M", "READ", 0x80000000)])[0]
            self.assertNotEqual(first, b"\x13\x00\x00\x00abcd")
            with self.assertRaisesRegex(RuntimeError, "separately addressed"):
                host.preflight_axi_mapping(transport, 3, record)
        self.assertFalse(record["verified"])
        self.assertTrue(record["restored"])
        self.assertEqual(record["observed_bytes_at_each_address"],
                         ["1032547698badcfe", "0123456789abcdef"])

    def test_mapping_errors_block_payload_entry_and_doorbell(self):
        for mode in ("burst_left", "write_left", "read_left"):
            report = {"passed": False}
            with self.subTest(mode=mode), self.transport(mode, mode) as transport:
                with self.assertRaisesRegex(RuntimeError, "mapping preflight"):
                    host.load_and_run(transport, image.prepare_image(self.elf, caps=3),
                                      self.base, report, True)
                self.assertEqual(host.read_debug(transport, [host.DONE]), [0])
            self.assertFalse(report["passed"])
            self.assertNotIn("load_metrics", report)
            evidence = json.loads((self.base / "report.json").read_text())
            self.assertFalse(evidence["axi_mapping_preflight"]["verified"])
            self.assertTrue(evidence["axi_mapping_preflight"]["restored"])
            entries = [json.loads(line) for line in (self.base / mode / "transport.jsonl").read_text().splitlines()]
            writes = [op for entry in entries for op in entry.get("operations", [])
                      if op["kind"] == "WRITE" and op["bus"] == "M"]
            self.assertEqual(len(writes), 3)  # Probe, then two single-beat restores.
            self.assertTrue(all(host.AXI_PREFLIGHT_ADDRESS <= op["address"] and
                                op["address"] + op["beats"] * 8 <= host.AXI_PREFLIGHT_ADDRESS + 16
                                for op in writes))

    def test_preflight_restore_error_blocks_launch_even_when_mapping_matches(self):
        report = {"passed": False}
        with self.transport() as transport:
            exchange = transport.exchange

            def fail_restore(operations):
                if operations[0].kind == "WRITE" and operations[0].beats == 1 and \
                        operations[0].address == host.AXI_PREFLIGHT_ADDRESS:
                    raise TransportError("injected restore failure")
                return exchange(operations)

            with patch.object(transport, "exchange", side_effect=fail_restore):
                with self.assertRaisesRegex(RuntimeError, "restoration failed"):
                    host.load_and_run(transport, image.prepare_image(self.elf, caps=3),
                                      self.base, report, True)
            self.assertEqual(transport.exchange([Operation("M", "READ", host.SCRATCH + 8)])[0], bytes(8))
        self.assertTrue(report["axi_mapping_preflight"]["burst_read_verified"])
        self.assertFalse(report["axi_mapping_preflight"]["verified"])
        self.assertFalse(report["axi_mapping_preflight"]["restored"])
        self.assertNotIn("load_metrics", report)

    def test_spm_probe_compares_burst_and_restores_original_words(self):
        address = host.SPM_PROBE_ADDRESS
        original = [bytes.fromhex("aabbccdd11223344"), bytes.fromhex("deadbeef13579bdf")]
        record = {}
        with self.transport() as transport:
            transport.exchange([Operation("M", "WRITE", address + 8 * i, data=word)
                                for i, word in enumerate(original)])
            host.probe_axi_spm_burst(transport, record)
            restored = transport.exchange([Operation("M", "READ", address + 8 * i)
                                           for i in range(2)])
        self.assertTrue(record["verified"])
        self.assertTrue(record["single_beat_verified"])
        self.assertTrue(record["restored"])
        self.assertEqual(restored, original)

    def test_spm_burst_mismatch_is_reported_and_restored(self):
        address = host.SPM_PROBE_ADDRESS
        original = [bytes.fromhex("aabbccdd11223344"), bytes.fromhex("deadbeef13579bdf")]
        record = {}
        with self.transport() as transport:
            transport.exchange([Operation("M", "WRITE", address + 8 * i, data=word)
                                for i, word in enumerate(original)])
            exchange = transport.exchange

            def wrong_burst(operations):
                if len(operations) == 1 and operations[0].kind == "READ" and \
                        operations[0].address == address and operations[0].beats == 2:
                    return [bytes(16)]
                return exchange(operations)

            with patch.object(transport, "exchange", side_effect=wrong_burst):
                with self.assertRaisesRegex(RuntimeError, "two-beat read differs"):
                    host.probe_axi_spm_burst(transport, record)
            restored = exchange([Operation("M", "READ", address + 8 * i)
                                 for i in range(2)])
        self.assertFalse(record["verified"])
        self.assertTrue(record["single_beat_verified"])
        self.assertTrue(record["restored"])
        self.assertEqual(restored, original)

    def test_spm_probe_cli_requires_explicit_destructive_gate(self):
        output = self.base / "spm"
        with self.assertRaises(SystemExit):
            host.main(["axi-spm-probe", "--out", str(output), "--full-reset-confirmed"])
        self.assertFalse(output.exists())

    def test_spm_probe_cli_writes_narrow_pass_report(self):
        output = self.base / "spm"

        def factory(directory, **kwargs):
            return self.transport("pass", str(Path(directory).relative_to(self.base)))

        with patch.object(host, "VivadoTransport", side_effect=factory):
            code = host.main(["axi-spm-probe", "--out", str(output),
                              "--full-reset-confirmed", "--destructive-spm-test-confirmed",
                              "--reset-jtag-axi"])
        self.assertEqual(code, 0)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["state"], "passed_axi_spm_burst_only")
        self.assertTrue(report["jtag_axi_reset_before_probe"])
        self.assertTrue(report["axi_spm_probe"]["restored"])
        self.assertFalse((output / "image.json").exists())
        entries = [json.loads(line) for line in
                   (output / "axi_spm_probe/transport.jsonl").read_text().splitlines()]
        reset_index = next(i for i, entry in enumerate(entries) if "reset" in entry)
        memory_index = next(i for i, entry in enumerate(entries)
                            if any(op["bus"] == "M" for op in entry.get("operations", [])))
        self.assertLess(reset_index, memory_index)
        self.assertIn("MOCK reset memory AXI core",
                      (output / "axi_spm_probe/vivado.log").read_text())
        self.assertRegex((output / "axi_spm_probe/vivado.log").read_text(),
                         r"HOST AXI two-beat READ address=0x1401ff00 "
                         r"before_refresh=[0-9a-f]{32} after_refresh=[0-9a-f]{32}")

    def test_spm_probe_reset_failure_prevents_memory_access(self):
        with self.transport("reset_error") as transport:
            with self.assertRaisesRegex(TransportError, "JTAG AXI reset failed"):
                transport.reset_memory_axi()
        entries = [json.loads(line) for line in
                   (self.base / "session/transport.jsonl").read_text().splitlines()]
        self.assertFalse(any("operations" in entry for entry in entries))

    def test_unaligned_adjacent_segments_preserve_outside_bytes(self):
        raw = self.base / "raw.bin"
        raw.write_bytes(bytes(range(23)))
        prepared = image.prepare_image(self.elf, [(0x100000FFB, raw)], 3)
        with self.transport() as transport:
            host.verified_load(transport, prepared, batch_chunks=2)
            left = transport.exchange([Operation("M", "READ", 0x100000FF8)])[0]
            right = transport.exchange([Operation("M", "READ", 0x100001000, 3)])[0]
            self.assertEqual(left + right, b"\xa5" * 3 + bytes(range(23)) + b"\xa5" * 6)

    def test_single_beat_unaligned_segment_preserves_outside_bytes(self):
        raw = self.base / "raw.bin"
        raw.write_bytes(bytes(range(23)))
        prepared = image.prepare_image(self.elf, [(0x100000FFB, raw)], 3)
        with self.transport(name="single_unaligned") as transport:
            records = host.verified_load(transport, prepared, batch_chunks=2,
                                         single_beat=True)
            self.assertTrue(all(record["verified"] for record in records))
            left = transport.exchange([Operation("M", "READ", 0x100000FF8)])[0]
            right = b"".join(transport.exchange(
                [Operation("M", "READ", 0x100001000 + 8 * i) for i in range(3)]))
            self.assertEqual(left + right, b"\xa5" * 3 + bytes(range(23)) + b"\xa5" * 6)
        entries = [json.loads(line) for line in
                   (self.base / "single_unaligned/transport.jsonl").read_text().splitlines()]
        self.assertTrue(all(op["beats"] == 1 for entry in entries
                            for op in entry.get("operations", []) if op["bus"] == "M"))

    def test_no_done_is_not_pass(self):
        with self.transport("no_done") as transport:
            with self.assertRaisesRegex(RuntimeError, "No done"):
                self.run_image(transport)
        self.assertTrue((self.base / "snapshot.json").exists())

    def test_magic_and_ready_checks_fail_closed(self):
        for mode, error in (("bad_magic", "mismatch"), ("not_ready", "not ready")):
            with self.subTest(mode=mode), self.transport(mode, mode) as transport:
                with self.assertRaisesRegex(RuntimeError, error):
                    self.run_image(transport)

    def test_recorded_loading_bus_error_prevents_launch(self):
        with self.transport("loading_error") as transport:
            with self.assertRaisesRegex(RuntimeError, "while loading"):
                self.run_image(transport)
            self.assertEqual(host.read_debug(transport, [host.DONE])[0], 0)

    def test_bad_execution_results_fail(self):
        for mode, error in (("no_retire", "retirement"), ("stale", "Run ID"),
                            ("software_error", "Software failed"), ("trap", "Software failed"),
                            ("bus_error", "DDR AXI error"), ("watchdog", "No done")):
            with self.subTest(mode=mode), self.transport(mode, mode) as transport:
                with self.assertRaisesRegex(RuntimeError, error):
                    self.run_image(transport)

    def test_watchdog_snapshot_not_overwritten(self):
        with self.transport("watchdog") as transport:
            with self.assertRaises(RuntimeError):
                self.run_image(transport)
            sequence = host.read_debug(transport, [host.SEQUENCE])[0]
            snapshot = host.capture_snapshot(transport, freeze=True)
            self.assertEqual(snapshot["snapshot_sequence"], sequence)
            self.assertTrue(snapshot["watchdog_snapshot"])

    def test_error_info_never_attributed_to_last_address(self):
        with self.transport("bus_error") as transport:
            with self.assertRaises(RuntimeError):
                self.run_image(transport)
        ddr = json.loads((self.base / "snapshot.json").read_text())["ddr1"]
        self.assertEqual(ddr["reserved_error_addr"], 0)
        self.assertNotIn("last_error_addr", ddr)
        self.assertEqual((ddr["error_response"], ddr["error_channel"], ddr["error_id"]), (3, "B", 171))

    def test_snapshot_uses_debug_only(self):
        with self.transport("debug_only") as transport:
            snapshot = host.capture_snapshot(transport)
            self.assertEqual(snapshot["identity"]["magic"], host.MAGIC)
        log = (self.base / "session/transport.jsonl").read_text()
        self.assertNotIn('"bus": "M"', log)

    def test_ddr1_snapshot_does_not_read_ddr2(self):
        with self.transport("ddr1_only") as transport:
            self.assertNotIn("ddr2", host.capture_snapshot(transport))
        entries = [json.loads(line) for line in (self.base / "session/transport.jsonl").read_text().splitlines()]
        self.assertFalse(any(op["address"] >= 0x200 for entry in entries for op in entry.get("operations", [])))

    def test_snapshot_retries_sequence_race(self):
        with self.transport("sequence_race") as transport:
            snapshot = host.capture_snapshot(transport)
            self.assertEqual(snapshot["snapshot_sequence"], 2)

    def test_batch_response_error_and_size_fail(self):
        for mode, error in (("response_error", "SLVERR"), ("wrong_width", "data width"),
                            ("incomplete", "did not complete")):
            with self.subTest(mode=mode), self.transport(mode, mode) as transport:
                with self.assertRaisesRegex(TransportError, error):
                    transport.exchange([Operation("M", "READ", 0x80000000)])

    def test_readback_mismatch_does_not_boot(self):
        with self.transport("corrupt") as transport:
            with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
                self.run_image(transport)
            self.assertEqual(host.read_debug(transport, [host.DONE])[0], 0)

    def test_duplicate_cell_fails_closed(self):
        with self.assertRaises(TransportError):
            with self.transport("duplicate"):
                pass

    def test_hung_memory_times_out_debug_session_still_works(self):
        with self.transport("hang_mem", timeout=0.1) as transport:
            with self.assertRaises(TransportError):
                transport.exchange([Operation("M", "READ", 0x80000000)])
        with self.transport("debug_only", "recovery") as transport:
            self.assertEqual(host.capture_snapshot(transport)["identity"]["abi"], 1)

    def test_mutated_image_is_never_launched(self):
        prepared = image.prepare_image(self.elf, caps=3)
        content = bytearray(self.elf.read_bytes())
        content[-1] ^= 1
        self.elf.write_bytes(content)
        with self.transport() as transport:
            with self.assertRaisesRegex(RuntimeError, "changed since preparation"):
                host.verified_load(transport, prepared)

    def test_ddr_test_success_only_writes_reserved_scratch(self):
        with self.transport() as transport:
            result = ddr_test.test_memory(transport, 3, True, True)
        self.assertTrue(result["cross_bank_alias_check"])
        self.assertEqual(len(result["records"]), 2)
        for record in result["records"]:
            self.assertTrue(record["verified"])
            self.assertEqual(record["expected_sha256"], record["readback_sha256"])
        entries = [json.loads(line) for line in (self.base / "session/transport.jsonl").read_text().splitlines()]
        writes = [op for entry in entries for op in entry.get("operations", []) if op["kind"] == "WRITE"]
        self.assertEqual(sum(op["beats"] * 8 for op in writes), 128 * 1024)
        for op in writes:
            self.assertTrue(any(r["address"] <= op["address"] and op["address"] + op["beats"] * 8 <=
                                r["bank_end_exclusive"] for r in result["records"]))
        self.assertEqual({r["address"] for r in result["edge_reads"]},
                         {0x80000000, 0xFFFFFFF8, 0x100000000, 0x17FFFFFF8})

    def test_ddr_alias_is_detected_after_both_writes(self):
        with self.transport("alias") as transport:
            with self.assertRaisesRegex(RuntimeError, "possible alias"):
                ddr_test.test_memory(transport, 3, True, True)

    def test_cli_success_is_reported_only_with_real_done_record(self):
        for mode, expected in (("pass", 0), ("no_done", 1)):
            output = self.base / mode

            def factory(directory, **kwargs):
                return self.transport(mode, str(Path(directory).relative_to(self.base)))

            with patch.object(host, "VivadoTransport", side_effect=factory):
                code = host.main(["load", "--elf", str(self.elf), "--out", str(output),
                                  "--full-reset-confirmed", "--seconds", "0.01"])
            self.assertEqual(code, expected)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["passed"], mode == "pass")
            self.assertTrue((output / "image.json").exists())

    def test_cli_failure_saves_evidence_and_recovers_with_debug_only(self):
        output = self.base / "cli"

        def factory(directory, **kwargs):
            mode = "response_error" if Path(directory).name == "load" else "debug_only"
            return self.transport(mode, str(Path(directory).relative_to(self.base)))

        with patch.object(host, "VivadoTransport", side_effect=factory):
            code = host.main(["load", "--elf", str(self.elf), "--out", str(output),
                              "--full-reset-confirmed"])
        self.assertEqual(code, 1)
        report = json.loads((output / "report.json").read_text())
        self.assertFalse(report["passed"])
        self.assertIn("SLVERR", report["error"])
        self.assertTrue((output / "snapshot.json").exists())


class PackageTests(unittest.TestCase):
    def test_exported_sources_match(self):
        for path in list(SOFTWARE.glob("host_*")) + [SOFTWARE / "fpga_debug.h"]:
            if path.is_file():
                self.assertEqual(path.read_bytes(), (EXPORTED / path.name).read_bytes(), path.name)

    def test_prebuilt_elfs_and_hashes(self):
        record = json.loads((SOFTWARE / "host_smoke_build.json").read_text())
        for name, digest in {**record["sources"], **record["outputs"]}.items():
            self.assertEqual(image.sha256_file(SOFTWARE / name), digest, name)
        for name in record["outputs"]:
            prepared = image.prepare_image(SOFTWARE / name)
            self.assertEqual(prepared.entry, 0x80000000)
            self.assertLess(sum(s.size for s in prepared.segments), 65536)


if __name__ == "__main__":
    unittest.main()
