import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

SPEC = importlib.util.spec_from_file_location(
    "jtag_linux_control", Path(__file__).with_name("jtag_linux_control.py"))
CONTROL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROL)


class JtagControlTests(unittest.TestCase):
    def exercise(self, failure=None, ethernet=False):
        events, reports = [], []

        def step(name, result=None):
            def invoke(*args, **kwargs):
                events.append(name)
                if name == failure:
                    raise RuntimeError(name + " failed")
                return result
            return invoke

        def load(*args, **kwargs):
            self.assertTrue(kwargs["launch_only"])
            self.assertTrue(kwargs["full_reset_confirmed"])
            if not ethernet:
                self.assertEqual(kwargs["batch_chunks"], 128)
            step("load")()

        def console(port, output, launch, seconds, marker):
            self.assertEqual(marker, b"Linux console, DDR and RVV handoff are alive")
            launch()
            return step("marker", {"marker_seen": True})()

        host = SimpleNamespace(
            identity=step("identity", {"caps": 1}),
            serial_module=lambda: SimpleNamespace(Serial=lambda *a, **k: contextlib.nullcontext()),
            wait_linux_console=console, load_and_run=load,
            write_json=lambda path, value: reports.append(dict(value)))
        transport = SimpleNamespace(ethernet_status=step("status", 0))
        integrated = SimpleNamespace(
            host=host, CAP_HOST=1,
            prepare_image=step("prepare", SimpleNamespace(manifest=lambda: {})),
            validate_image=step("validate"),
            VivadoTransport=lambda *a, **k: contextlib.nullcontext(transport),
            cold_guard=step("cold", {}), loader_status=step("unlocked", {}),
            lock_and_drain=step("isolate", {"isolated": True}), load_and_run=load)
        with tempfile.TemporaryDirectory() as directory:
            argv = ["jtag_linux_control.py", "--tools", directory, "--base", directory,
                    "--image", "Image", "--probes", "image.ltx", "--out",
                    str(Path(directory) / "run"), "--vivado", "unused"]
            if ethernet:
                argv += ["--ethernet-host", "192.168.1.10"]
            with patch.dict(sys.modules, {"ara_load": integrated}), \
                    patch.object(CONTROL.socket, "socket", return_value=MagicMock()), \
                    patch.object(sys, "argv", argv), patch.object(sys, "path", list(sys.path)), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = CONTROL.main()
        return code, events, reports[-1]

    def test_ethernet_delegates_locking_to_integrated_loader(self):
        code, events, report = self.exercise(ethernet=True)
        self.assertEqual(code, 0)
        self.assertTrue(report["ethernet_packets_used"])
        self.assertNotIn("isolate", events)
        self.assertLess(events.index("cold"), events.index("load"))
        code, events, report = self.exercise("cold", ethernet=True)
        self.assertEqual(code, 1)
        self.assertNotIn("load", events)

    def test_gates_precede_load(self):
        code, events, report = self.exercise()
        self.assertEqual(code, 0)
        self.assertEqual(events, ["prepare", "validate", "identity", "cold", "status",
                                  "unlocked", "isolate", "load", "marker"])
        self.assertTrue(report["passed"])
        self.assertFalse(report["ethernet_packets_used"])

    def test_each_failed_gate_blocks_loading(self):
        for failure in ("validate", "identity", "cold", "unlocked", "isolate"):
            with self.subTest(failure=failure):
                code, events, report = self.exercise(failure)
                self.assertEqual(code, 1)
                self.assertNotIn("load", events)
                self.assertFalse(report["passed"])

    def test_load_or_marker_failure_is_not_a_boot_pass(self):
        for failure in ("load", "marker"):
            with self.subTest(failure=failure):
                code, _, report = self.exercise(failure)
                self.assertEqual(code, 1)
                self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
