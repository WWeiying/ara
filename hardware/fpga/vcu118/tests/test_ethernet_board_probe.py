"""Offline safety gates for the isolated J10 board probe."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ethernet/board_probe.py"
SPEC = importlib.util.spec_from_file_location("ethernet_board_probe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BoardProbeTests(unittest.TestCase):
    def test_requires_explicit_confirmation_before_output_or_vivado(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            with self.assertRaises(SystemExit):
                MODULE.main(["--out", str(output)])
            self.assertFalse(output.exists())

    def test_build_hash_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp)
            (build / "eth_diag.bit").write_bytes(b"bit")
            (build / "eth_diag.ltx").write_bytes(b"ltx")
            record = {
                "state": "built_needs_manual_review_and_board_test",
                "full_license_bitstream_generated": True,
                "artifacts": {name: {"sha256": MODULE.sha256(build / name)}
                              for name in ("eth_diag.bit", "eth_diag.ltx")},
            }
            (build / "build.json").write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(MODULE.checked_build(build), (build / "eth_diag.bit", build / "eth_diag.ltx"))
            (build / "eth_diag.bit").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                MODULE.checked_build(build)

    def test_tcl_mock_programming_and_status(self):
        run = subprocess.run(["tclsh", str(Path(__file__).with_suffix(".tcl"))],
                             capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("MOCK_BOARD_PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
