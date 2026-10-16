import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("current_restore", Path(__file__).with_name("read_current_restore.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
IMAGE = Path(__file__).parents[1] / "artifacts/Image"
patch_spec = importlib.util.spec_from_file_location("order_control", Path(__file__).with_name("patch_restore_order_control.py"))
control = importlib.util.module_from_spec(patch_spec)
patch_spec.loader.exec_module(control)
console_spec = importlib.util.spec_from_file_location("console_check", Path(__file__).with_name("check_linux_console.py"))
console_check = importlib.util.module_from_spec(console_spec)
console_spec.loader.exec_module(console_check)


class ProbeTest(unittest.TestCase):
    def test_paced_console_preserves_command_and_checks_response(self):
        writes = []
        reads = iter((b"\n/ # ", b"\nARA_SHELL_MEMORY_OK\n"))

        class Serial:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def write(self, data):
                writes.append(data)

            def read(self, size):
                return next(reads)

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "console"
            argv = ["check", "--port", "unused", "--out", str(out), "--tx-gap", "0.02", "--clear-line"]
            with patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=Serial, SerialException=OSError)}), \
                    patch.object(sys, "argv", argv), patch.object(console_check.time, "sleep"), patch("builtins.print"):
                self.assertEqual(console_check.main(), 0)
            self.assertEqual(writes[:2], [b"\x03", b"\n"])
            self.assertTrue(all(len(chunk) == 1 for chunk in writes))
            self.assertIn(b"sha256sum /tmp/ara_console_check.bin", b"".join(writes))
            self.assertTrue(json.loads((out / "report.json").read_text())["passed"])

    def test_order_control_preserves_other_bytes(self):
        source = IMAGE.read_bytes()
        result = control.patch_image(source)
        self.assertEqual(len(result), len(source))
        self.assertEqual(result[:0x15e80], source[:0x15e80])
        self.assertEqual(result[0x15e9e:], source[0x15e9e:])
        self.assertEqual(result[0x15e80:0x15e9a], source[0x15e84:0x15e9e])
        self.assertEqual(result[0x15e9a:0x15e9e], bytes.fromhex("0f003003"))
        with self.assertRaises(ValueError):
            control.patch_image(result)

    def test_mappings_reject_unreviewed_address(self):
        self.assertEqual(probe.physical(0xffffffff81a32000), 0x81c32000)
        self.assertEqual(probe.physical(0xffffffd602e00b80), 0x82e00b80)
        for va in (0, 0x80000000, 0xffffffd580000000):
            with self.assertRaises(ValueError):
                probe.physical(va)

    def test_pinned_image_read_path(self):
        image = IMAGE.read_bytes()
        task = probe.DIRECT_BASE + 0x2e00000
        runqueue = probe.DIRECT_BASE + 0x2400000
        percpu = (runqueue - 0xffffffff80e48940) & probe.MASK
        memory = {}

        def put(pa, data):
            for i in range(0, len(data), 8):
                memory[pa+i] = data[i:i+8]

        def word(pa, value):
            put(pa, struct.pack("<Q", value))

        for offset, size in ((0x5e5c8, 48), (0x15e98, 32)):
            put(0x80200000+offset, image[offset:offset+size])
        word(0x81c61620, percpu)
        word(0x82400a80, task)
        put(0x82e00b80, struct.pack("<6Q", 0, 0, 1 << 63, 0, 128, probe.DIRECT_BASE+0x2e10000))
        word(0x81c32000+((task >> 30) & 511)*8, (0x82000000 >> 12) << 10 | 1)
        word(0x82000000+((task >> 21) & 511)*8, (0x82e00000 >> 12) << 10 | 0xcf)

        class Operation:
            def __init__(self, bus, kind, address):
                assert bus == "M" and kind == "READ"
                self.address = address

        class Transport:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def exchange(self, ops):
                return [memory[op.address] for op in ops]

        count = 0

        def snapshot(t):
            nonlocal count
            count += 1
            return {"core": {"head_pc": 0xffffffff80015e9a, "retired": 7, "cycles": count}}

        modules = {"host_transport": types.SimpleNamespace(Operation=Operation, VivadoTransport=Transport),
                   "host_load": types.SimpleNamespace(capture_snapshot=snapshot)}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result"
            argv = ["probe", "--image", str(IMAGE), "--software", tmp,
                    "--probes", "unused", "--vivado", "unused", "--out", str(out)]
            with patch.dict(sys.modules, modules), patch.object(sys, "argv", argv), patch("builtins.print"):
                probe.main()
            result = json.loads((out / "report.json").read_text())
            self.assertTrue(result["stable_execution"])
            self.assertTrue(result["stable_memory"])
            self.assertEqual(result["samples"][0]["task_va"], hex(task))
            walk = result["samples"][0]["kernel_page_walk"]
            self.assertEqual(walk["page_bytes"], 0x200000)
            self.assertEqual(walk["physical"], "0x82e00b80")
            self.assertTrue(walk["predicted_ni"])


if __name__ == "__main__":
    unittest.main()
