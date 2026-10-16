import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "preclock_loader_phy", Path(__file__).with_name("preclock_loader_phy.py"))
CONTROL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROL)


class PreclockTests(unittest.TestCase):
    def exercise(self, fail_guard=False, fail_xsct=False):
        events = []

        def guard(t):
            events.append("guard")
            if fail_guard:
                raise RuntimeError("not cold")
            return {"cold": True}

        def run(command, **kwargs):
            events.append("xsct")
            self.assertEqual(command[-1], "--cold-board-confirmed")
            self.assertTrue(kwargs["check"])
            self.assertEqual(kwargs["timeout"], 60)
            if fail_xsct:
                raise subprocess.CalledProcessError(1, command)

        module = SimpleNamespace(fresh_guard=guard, load=SimpleNamespace(
            VivadoTransport=lambda *a, **k: contextlib.nullcontext(object())))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            argv = ["preclock_loader_phy.py", "--tools", directory, "--probes", "x.ltx",
                    "--out", str(out), "--vivado", "unused", "--xsct", "unused"]
            with patch.dict(sys.modules, {"ara_init": module}), \
                    patch.object(sys, "argv", argv), patch.object(sys, "path", list(sys.path)), \
                    patch.object(CONTROL.subprocess, "run", run), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = CONTROL.main()
            report = json.loads((out / "report.json").read_text())
        return code, events, report

    def test_guard_precedes_phy_access(self):
        code, events, report = self.exercise()
        self.assertEqual((code, events), (0, ["guard", "xsct"]))
        self.assertEqual(report["state"], "clock_prepared_firmware_not_started")

    def test_failed_guard_blocks_phy_access(self):
        code, events, report = self.exercise(fail_guard=True)
        self.assertEqual((code, events), (1, ["guard"]))
        self.assertFalse(report["passed"])

    def test_failed_xsct_is_not_success(self):
        code, _, report = self.exercise(fail_xsct=True)
        self.assertEqual(code, 1)
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
