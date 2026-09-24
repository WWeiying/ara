#!/usr/bin/env python3
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import host_axi_netlist as inspect


class NetlistTests(unittest.TestCase):
    def fixture(self, root):
        probes = root / "design.ltx"
        checkpoint = root / "design_routed.dcp"
        probes.write_bytes(b"mock probes")
        checkpoint.write_bytes(b"mock checkpoint")
        metadata = {"Profile": "host", "Checkpoint": str(checkpoint),
                    "CheckpointSHA256": inspect.digest(checkpoint).upper(),
                    "Outputs": [{"Algorithm": "SHA256", "Hash": inspect.digest(probes).upper()}]}
        probes.with_name("bitstream.json").write_text(json.dumps(metadata), encoding="utf-8-sig")
        return probes, checkpoint

    def test_bom_metadata_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            probes, checkpoint = self.fixture(Path(tmp))
            self.assertEqual(inspect.checkpoint_for(probes)[0], checkpoint)

    def test_checkpoint_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            probes, checkpoint = self.fixture(Path(tmp))
            checkpoint.write_bytes(b"different checkpoint")
            with self.assertRaisesRegex(ValueError, "Checkpoint SHA256"):
                inspect.checkpoint_for(probes)

    def test_probes_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            probes, _ = self.fixture(Path(tmp))
            probes.write_bytes(b"other probes")
            with self.assertRaisesRegex(ValueError, "Probes SHA256"):
                inspect.checkpoint_for(probes)

    def test_missing_metadata_never_launches_vivado(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(inspect.subprocess, "run") as run:
            probes = Path(tmp) / "orphan.ltx"
            probes.touch()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(inspect.main([str(probes)]), 1)
            run.assert_not_called()

    def test_runner_accepts_complete_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            probes, checkpoint = self.fixture(root)

            def run(command, **kwargs):
                self.assertEqual(command[-2], str(checkpoint))
                self.assertIn("-mode", command)
                output = Path(command[-1])
                (output / "axi_netlist.rpt").write_text("SIZE arsize bits=011\nINSPECTION_COMPLETE\n")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(inspect.Path, "cwd", return_value=root), \
                 patch.object(inspect.shutil, "which", return_value="vivado.bat"), \
                 patch.object(inspect.subprocess, "run", side_effect=run), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(inspect.main([str(probes)]), 0)
            records = list((root / "axi_netlists").glob("*/inspection.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text())
            self.assertTrue(record["collected"])
            self.assertFalse(record["hardware_access"])

    def test_zero_exit_without_report_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            probes, _ = self.fixture(root)
            with patch.object(inspect.Path, "cwd", return_value=root), \
                 patch.object(inspect.shutil, "which", return_value="vivado.bat"), \
                 patch.object(inspect.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(inspect.main([str(probes)]), 1)
            record = json.loads(next((root / "axi_netlists").glob("*/inspection.json")).read_text())
            self.assertFalse(record["collected"])
            self.assertIn("error", record)

    def test_tcl_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(["tclsh", str(Path(__file__).with_suffix(".tcl")), tmp],
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS", result.stdout)

    def test_probes_from_latest_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "axi_netlists/run"
            old.mkdir(parents=True)
            expected = root / "matching.ltx"
            (old / "inspection.json").write_text(json.dumps({"bitstream_metadata": {
                "Outputs": [{"Path": str(root / "design.bit")}, {"Path": str(expected)}]}}))
            self.assertEqual(inspect.probes_from_last(root), expected)

    def test_full_export_and_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            probes, checkpoint = self.fixture(root)

            def run(command, **kwargs):
                self.assertEqual(command[-3], str(checkpoint))
                self.assertEqual(command[-1], "1")
                output = Path(command[-2])
                (output / "axi_netlist.rpt").write_text("INSPECTION_COMPLETE\n")
                (output / "full_design.v").write_text("module full; endmodule\n")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(inspect.Path, "cwd", return_value=root), \
                 patch.object(inspect.shutil, "which", return_value="vivado.bat"), \
                 patch.object(inspect.subprocess, "run", side_effect=run), \
                 patch("host_axi_upload.main", return_value=0) as upload, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(inspect.main([str(probes), "--full", "--upload"]), 0)
            upload.assert_called_once()
            record = json.loads(next((root / "axi_netlists").glob("*/inspection.json")).read_text())
            self.assertTrue(record["collected"])
            self.assertTrue(record["full_export"])

    def test_missing_full_netlist_never_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            probes, _ = self.fixture(root)

            def run(command, **kwargs):
                (Path(command[-2]) / "axi_netlist.rpt").write_text("INSPECTION_COMPLETE\n")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(inspect.Path, "cwd", return_value=root), \
                 patch.object(inspect.shutil, "which", return_value="vivado.bat"), \
                 patch.object(inspect.subprocess, "run", side_effect=run), \
                 patch("host_axi_upload.main") as upload, \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(inspect.main([str(probes), "--full", "--upload"]), 1)
            upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
