from pathlib import Path
import json
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ethernet"))
import ara_load as loader
from host_transport import VivadoTransport, TransportError

MAGIC = 0x45544831
LOCKED = MAGIC | (3 << 32)


class ProtocolTests(unittest.TestCase):
    def test_bounds(self):
        image = SimpleNamespace(caps=1, segments=[SimpleNamespace(address=0xFEFEFFF8, size=8)])
        loader.validate_image(image)
        image.segments[0].size = 9
        with self.assertRaises(ValueError):
            loader.validate_image(image)

    def test_lock_checks(self):
        loader.loader_status(MAGIC)
        loader.loader_status(LOCKED, locked=True)
        for bad in (MAGIC, LOCKED | (1 << 64), LOCKED | (1 << 192),
                    LOCKED | (1 << 34), LOCKED | (1 << 224), 0):
            with self.subTest(status=bad), self.assertRaises(RuntimeError):
                loader.loader_status(bad, locked=True)

    def test_drain_and_stable_ack(self):
        transport = Mock()
        transport.ethernet_status.side_effect = [MAGIC, MAGIC | (1 << 32), LOCKED, LOCKED]
        with patch.object(loader.time, "sleep"):
            self.assertTrue(loader.lock_and_drain(transport)["isolated"])
        self.assertEqual(transport.ethernet_status.call_args_list[0].kwargs, {"lock": True})

    def test_no_drain_no_launch(self):
        transport = Mock()
        transport.ethernet_status.return_value = MAGIC | (1 << 32)
        with patch.object(loader.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaises(TimeoutError):
                loader.lock_and_drain(transport)

    def test_firmware_identity_rejects_standalone(self):
        sock = Mock()
        with patch.object(loader.secrets, "randbits", return_value=42):
            for limit in (0xFF000000, loader.APP_LIMIT):
                sock.recv.return_value = loader.fast.HEADER.pack(b"AFLD", 42, 0x8004, 0, 0x80000000, limit)
                if limit == loader.APP_LIMIT:
                    self.assertEqual(loader.firmware_identity(sock)["application_end"], limit)
                else:
                    with self.assertRaisesRegex(RuntimeError, "firmware profile"):
                        loader.firmware_identity(sock)

    def test_rom_hash_and_single_beats(self):
        expected = loader.rom_bytes()
        transport = Mock()
        def read(operations):
            self.assertTrue(all(op.kind == "READ" and op.beats == 1 for op in operations))
            return [expected[op.address-loader.ROM_BASE:op.address-loader.ROM_BASE+8] for op in operations]
        transport.exchange.side_effect = read
        self.assertEqual(loader.verify_rom(transport), loader.REVIEWED_ROM_SHA256)
        transport.exchange.side_effect = lambda ops: [bytes(8) for _ in ops]
        with self.assertRaisesRegex(RuntimeError, "ROM differs"):
            loader.verify_rom(transport)

    def test_cold_guard_rejects_old_ddr_activity(self):
        snapshot = {"identity": {"caps": 1},
                    "core": {"last_pc": loader.ROM_BASE + 0x842, "trap_count": 0},
                    "ddr1": dict.fromkeys(("ar_count", "aw_count", "r_bytes", "w_bytes",
                                           "read_outstanding", "write_outstanding", "error_count"), 0)}
        with patch.object(loader.host, "read_debug", return_value=[0, 0]), \
                patch.object(loader.host, "check_passive_boot"), \
                patch.object(loader.host, "capture_snapshot", return_value=snapshot):
            transport = Mock()
            transport.exchange.return_value = [bytes(8), b"\xff" + bytes(7)]
            loader.cold_guard(transport)
            snapshot["ddr1"]["ar_count"] = 1
            with self.assertRaisesRegex(RuntimeError, "cold-cache"):
                loader.cold_guard(transport)

    def test_orchestration_never_launches_after_failed_verification(self):
        image = SimpleNamespace(caps=1, entry=0x80000000,
            segments=[SimpleNamespace(address=0x80000000, size=8)], manifest=lambda: {})
        for failure in ("transfer", "drain", "cold", "success"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                report = {}
                transport = Mock()
                transport.ethernet_status.return_value = MAGIC
                with patch.object(loader.host, "identity", return_value={"caps": 1}), \
                        patch.object(loader, "cold_guard", return_value={}) as cold, \
                        patch.object(loader, "verify_rom", return_value="hash"), \
                        patch.object(loader.host, "check_passive_boot", return_value=bytes(4)), \
                        patch.object(loader, "firmware_identity", return_value={}), \
                        patch.object(loader.fast, "transfer_segment", return_value={}) as transfer, \
                        patch.object(loader, "lock_and_drain", return_value={}) as drain, \
                        patch.object(loader.host, "write_debug"), \
                        patch.object(loader.host, "_launch_verified") as launch:
                    if failure == "transfer": transfer.side_effect = ValueError("corrupt")
                    if failure == "drain": drain.side_effect = TimeoutError("pending")
                    if failure == "cold": cold.side_effect = [{}, RuntimeError("DDR activity")]
                    if failure == "success":
                        transport.ethernet_status.side_effect = [MAGIC, LOCKED, LOCKED]
                        launch.side_effect = lambda *args, **kwargs: kwargs["before_doorbell"]()
                        loader.load_and_run(transport, Mock(), image, tmp, report, True)
                        launch.assert_called_once()
                        self.assertIn("before_doorbell", launch.call_args.kwargs)
                    else:
                        with self.assertRaises((ValueError, RuntimeError, TimeoutError)):
                            loader.load_and_run(transport, Mock(), image, tmp, report, True)
                        launch.assert_not_called()

    def test_real_launch_guard_and_doorbell_order(self):
        host = loader.host
        image = SimpleNamespace(entry=0x80000000)
        entry = image.entry.to_bytes(8, "little")
        for failure in ("entry", "ready", "controls", "guard", None):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                events = []
                report = {}
                transport = Mock()
                def exchange(ops):
                    events.extend((op.kind, op.address) for op in ops)
                    return [None, bytes(8) if failure == "entry" else entry]
                transport.exchange.side_effect = exchange
                def guard():
                    events.append(("GUARD", None))
                    if failure == "guard":
                        raise RuntimeError("loader not isolated")
                controls = [0, 7, 0xffffffff, 1 if failure == "controls" else 0]
                with patch.object(host, "read_debug", side_effect=[
                        [0 if failure == "ready" else 7], controls]), \
                        patch.object(host, "write_debug"):
                    call = lambda: host._launch_verified(
                        transport, image, tmp, report, bytes(4), 7, 1,
                        launch_only=True, before_doorbell=guard)
                    if failure:
                        with self.assertRaises(RuntimeError):
                            call()
                        self.assertNotIn(("WRITE", host.SCRATCH + 8), events)
                        self.assertNotIn("execution_started", report)
                    else:
                        call()
                        self.assertEqual(events[-2:], [
                            ("GUARD", None), ("WRITE", host.SCRATCH + 8)])
                        self.assertTrue(report["execution_started"])

    def test_linux_mode_uses_uart_marker_after_verified_launch(self):
        image = SimpleNamespace(caps=1, segments=[], manifest=lambda: {})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "linux"
            with patch.object(loader, "prepare_image", return_value=image) as prepare, \
                    patch.object(loader, "VivadoTransport", return_value=MagicMock()), \
                    patch.object(loader.socket, "socket", return_value=MagicMock()), \
                    patch.object(loader.host, "serial_module", return_value=SimpleNamespace(Serial=MagicMock())), \
                    patch.object(loader.host, "wait_linux_console") as wait, \
                    patch.object(loader, "load_and_run") as launch:
                wait.side_effect = lambda port, output, start, seconds: (start(), {"marker_seen": True})[1]
                self.assertEqual(loader.main(["--elf", str(Path(tmp) / "fw_jump.elf"),
                    "--probes", str(Path(tmp) / "image.ltx"), "--out", str(out),
                    "--full-reset-confirmed", "--linux", "--port", "COM6"]), 0)
                self.assertTrue(prepare.call_args.kwargs["allow_dynamic"])
                self.assertTrue(launch.call_args.kwargs["launch_only"])
                self.assertEqual(json.loads((out / "report.json").read_text())["state"],
                                 "passed_linux_init_marker")


@unittest.skipUnless(shutil.which("tclsh"), "Tcl required")
class TclTests(unittest.TestCase):
    def test_real_transport_read_lock_and_bad_identity(self):
        for mode in ("pass", "eth_absent", "eth_duplicate", "eth_width", "eth_magic"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                command = [shutil.which("tclsh"), str(HERE / "test_host_mock.tcl"), mode,
                           str(HERE.parent / "software/host_vivado.tcl")]
                with VivadoTransport(tmp, command=command, timeout=2, startup_timeout=2) as transport:
                    if mode == "pass":
                        self.assertEqual(transport.ethernet_status(), MAGIC)
                        transport.ethernet_status(lock=True)
                        self.assertEqual(transport.ethernet_status(), MAGIC | 1 << 32)
                    else:
                        with self.assertRaises(TransportError):
                            transport.ethernet_status(lock=True)


if __name__ == "__main__":
    unittest.main()
