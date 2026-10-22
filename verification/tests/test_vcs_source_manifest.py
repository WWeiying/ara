import tempfile
import unittest
from pathlib import Path

from ara_verify.vcs_source_manifest import collect, main


class VcsSourceManifestTests(unittest.TestCase):
    def test_capture_detects_source_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("hardware/tb/dpi", "config", "inc"):
                (root / relative).mkdir(parents=True)
            for relative in ("hardware/Makefile", "Bender.yml", "Bender.lock",
                             "config/default.mk", "config/sram.mk", "inc/header.svh",
                             "hardware/tb/dpi/elfloader.cc", "source.sv", "uvm.sv"):
                (root / relative).write_text(relative)
            filelist = root / "files.f"
            filelist.write_text(f"+define+TEST\n+incdir+{root / 'inc'}\n{root / 'source.sv'}\n")
            records = collect(filelist, root, [root / "uvm.sv"])
            names = {Path(row["path"]).name for row in records}
            self.assertTrue({"files.f", "source.sv", "header.svh", "elfloader.cc",
                             "uvm.sv"}.issubset(names))

            import sys
            from unittest.mock import patch

            output = root / "manifest.json"
            argv = ["vcs_source_manifest.py", "--filelist", str(filelist),
                    "--repo-root", str(root), "--extra-source", str(root / "uvm.sv"),
                    "--output", str(output)]
            with patch.object(sys, "argv", argv):
                self.assertEqual(main(), 0)
            with patch.object(sys, "argv", ["vcs_source_manifest.py", "--output",
                                          str(output), "--check"]):
                self.assertEqual(main(), 0)
            (root / "source.sv").write_text("changed")
            with patch.object(sys, "argv", ["vcs_source_manifest.py", "--output",
                                          str(output), "--check"]):
                self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
