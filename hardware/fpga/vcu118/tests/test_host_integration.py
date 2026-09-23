"""Check optional board feature integration without changing the CPU snapshot."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
PKG = HERE.parent / "ara_dsa_vcu118"
sys.path.insert(0, str(HERE))
from host_debug_fpga import patch_soc_debug


class HostIntegration(unittest.TestCase):
    def test_digital_evidence_matches_inputs(self):
        evidence = HERE / "results/20260922_host"
        debug = json.loads((evidence / "debug/result.json").read_text())
        for name, expected in debug["inputs"].items():
            source = HERE / ("tests" if name.endswith("_tb.sv") else "rtl") / name
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected, name)
        self.assertEqual(hashlib.sha256((evidence / "debug/run.log").read_bytes()).hexdigest(),
                         debug["run_sha256"])
        root = HERE.parents[2]
        jtag = json.loads((evidence / "jtag/result.json").read_text())
        for name, expected in jtag["inputs"].items():
            source = {"board_sha256": PKG / "rtl/board/ara_dsa_vcu118.sv",
                      "dram_sha256": PKG / "rtl/board/dram_wrapper_xilinx.sv"}.get(name, root / name)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected, name)
        self.assertEqual(hashlib.sha256((evidence / "jtag/run.log").read_bytes()).hexdigest(),
                         jtag["run_sha256"])
        ddr = json.loads((evidence / "ddr/result.json").read_text())
        for name, expected in ddr["sources"].items():
            if "/hardware/" in name:
                source = root / "hardware" / name.split("/hardware/", 1)[1]
            else:
                self.assertTrue(name.endswith("/dram_wrapper_xilinx.sv"))
                source = PKG / "rtl/board/dram_wrapper_xilinx.sv"
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected, name)
        for name, expected in ddr["runs"].items():
            self.assertEqual(hashlib.sha256((evidence / "ddr" / (name + ".log")).read_bytes()).hexdigest(),
                             expected, name)

    def test_source_list_and_copies(self):
        manifest = json.loads((PKG / "manifest.json").read_text())
        for source in (HERE / "rtl").glob("*.sv"):
            name = "rtl/board/" + source.name
            self.assertEqual(manifest["files"].count(name), 1)
            self.assertEqual(source.read_bytes(), (PKG / name).read_bytes())
            self.assertIn("{" + name + "}", (PKG / "scripts/sources.tcl").read_text())
        for define in ("ARA_FPGA_HOST", "ARA_FPGA_DDR2"):
            self.assertNotIn(define, manifest["defines"])

    def test_probe_patch_is_exact_and_repeatable(self):
        name = "hardware/fpga/ara_dsa_vcu118/rtl/cheshire/hw/cheshire_soc.sv"
        before = subprocess.check_output(["git", "show", "ae313316:" + name],
                                         cwd=HERE, text=True)
        after = patch_soc_debug(before)
        self.assertEqual(after, (PKG / "rtl/cheshire/hw/cheshire_soc.sv").read_text())
        self.assertEqual(patch_soc_debug(after), after)
        with self.assertRaises(ValueError):
            patch_soc_debug("")

    def test_baseline_software_and_cpu_fixes_unchanged(self):
        names = ["rtl/cheshire/hw/bootrom/cheshire_bootrom.sv",
                 "software/reference/params.h", "software/smoke.elf",
                 "rtl/cva6/core/load_unit.sv", "rtl/ara/hardware/src/lane/vmfpu.sv",
                 "linux/artifacts/Image", "linux/artifacts/fw_jump.elf",
                 "linux/artifacts/initramfs.cpio", "linux/artifacts/ara_vcu118.dtb"]
        for name in names:
            with self.subTest(name=name):
                before = subprocess.check_output([
                    "git", "show", "ae313316:hardware/fpga/ara_dsa_vcu118/" + name], cwd=HERE)
                self.assertEqual(hashlib.sha256(before).digest(),
                                 hashlib.sha256((PKG / name).read_bytes()).digest())


if __name__ == "__main__":
    unittest.main()
