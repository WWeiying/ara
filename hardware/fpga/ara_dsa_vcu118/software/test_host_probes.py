#!/usr/bin/env python3
"""Focused host loader probes-file argument checks; no Vivado or board required."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from host_transport import VivadoTransport


class HostProbesTests(unittest.TestCase):
    def test_transport_passes_probes_as_eighth_tcl_argument(self):
        with tempfile.TemporaryDirectory() as temp:
            probes = Path(temp) / "matching probes.ltx"
            transport = VivadoTransport(Path(temp) / "out", probes=probes)
            self.assertEqual(len(transport.arguments), 6)
            self.assertEqual(transport.arguments[-1], probes.as_posix())
            self.assertEqual(VivadoTransport(Path(temp) / "out").arguments[-1], "-")

    def test_missing_probes_rejected_before_evidence_directory_is_created(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "evidence"
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("host_load.py")),
                 "snapshot", "--probes", str(Path(temp) / "missing.ltx"),
                 "--out", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Debug probes file not found", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
