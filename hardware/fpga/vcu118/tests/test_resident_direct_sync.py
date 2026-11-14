"""Check the frozen Direct-U migration without using mutable CVA6 dependencies."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[2] / "ara_dsa_vcu118"
PROVENANCE = PACKAGE / "provenance/resident_direct_20261114"
GATE_SHA256 = "df5ec3839cca84929468683c502e98e6cb8233771e05e5d2bfbe22dda7e6430a"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ResidentDirectSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((PROVENANCE / "baseline-current-hashes.json").read_text())
        cls.manifest = json.loads((PACKAGE / "manifest.json").read_text())

    def test_exact_reviewed_gate_and_outputs(self):
        self.assertEqual(digest(PROVENANCE / "cva6-akv-direct-gate.patch"), GATE_SHA256)
        for name, expected in self.contract["current"].items():
            self.assertEqual(digest(PACKAGE / "rtl/cva6" / name), expected, name)
        for name, row in self.contract["artifacts"].items():
            self.assertEqual(digest(PROVENANCE / name), row["sha256"], name)

    def test_reverse_and_forward_patch_reproduce_exact_preimages(self):
        with tempfile.TemporaryDirectory(prefix="resident-direct-sync-") as tmp:
            root = Path(tmp)
            for name in self.contract["current"]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(PACKAGE / "rtl/cva6" / name, target)
            command = ["git", "-C", "/tmp", "apply", "--unsafe-paths", "--directory=" + tmp]
            patch = str(PROVENANCE / "cva6-akv-direct-gate.patch")
            subprocess.run(command + ["--reverse", patch], check=True, capture_output=True)
            for name, expected in self.contract["baseline"].items():
                self.assertEqual(digest(root / name), expected, name)
            subprocess.run(command + [patch], check=True, capture_output=True)
            for name, expected in self.contract["current"].items():
                self.assertEqual(digest(root / name), expected, name)

    def test_four_files_are_real_compilation_inputs(self):
        preimages = {r["file"]: r["source_sha256"]
                     for r in self.manifest["source_hashes_before_integration"]}
        tcl = (PACKAGE / "scripts/sources.tcl").read_text()
        for name, expected in self.contract["current"].items():
            relative = "rtl/cva6/" + name
            self.assertEqual(self.manifest["files"].count(relative), 1, relative)
            self.assertIn("{" + relative + "}", tcl)
            self.assertEqual(preimages[relative], expected, relative)

    def test_original_configuration_and_all_on_selectors(self):
        self.assertEqual(self.manifest["soc_clock_mhz"], 50)
        self.assertEqual(self.manifest["optimization_profile"], "candidate_all")
        defines = self.manifest["defines"]
        self.assertEqual(defines["NR_LANES"], 4)
        self.assertEqual(defines["VLEN"], 1024)
        for name in ("ARA_QBS_ENABLE", "ARA_AKV_ENABLE", "ARA_AKV_V2_ENABLE",
                     "ARA_SHARED_SIMD_MUL", "ARA_SHARED_FMA", "ARA_QBS_LANE_MUL_ENABLE",
                     "ARA_AKV_RESIDENT_PV_ENABLE", "ARA_AKV_RESIDENT_QK_ENABLE"):
            self.assertEqual(defines[name], 1, name)

    def test_candidate_is_not_claimed_as_board_acceptance(self):
        migration = self.manifest["resident_direct_migration"]
        self.assertTrue(migration["source_only"])
        self.assertFalse(migration["bitstream_updated"])
        self.assertFalse(migration["hardware_accepted"])
        record = json.loads((PACKAGE / migration["record"]).read_text())
        self.assertFalse(record["board_modified"])
        self.assertFalse(record["vivado_started"])
        self.assertEqual(record["patch_sha256"], GATE_SHA256)
        inherited = json.loads((PROVENANCE / "focused-validation.json").read_text())
        self.assertEqual(inherited["focused_test"]["checks"], 77878)
        self.assertFalse(inherited["focused_test"]["board_tested"])


if __name__ == "__main__":
    unittest.main()
