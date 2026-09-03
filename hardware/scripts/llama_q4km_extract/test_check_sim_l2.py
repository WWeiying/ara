#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check-sim-l2.sh")


class CheckSimulatorContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sim_dir = self.root / "sim"
        self.sim_dir.mkdir()
        self.elf = self.root / "test.elf"
        self.elf.touch()
        self.readelf = self.root / "readelf"
        self.readelf.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' "
            "'LOAD 0x000000 0x0000000080000000 0x0000000080000000 "
            "0x000100 0x000100 R E 0x1000'\n",
            encoding="utf-8",
        )
        self.readelf.chmod(0o755)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_checker(self, implementation: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["READELF"] = str(self.readelf)
        return subprocess.run(
            [str(SCRIPT), str(self.sim_dir), str(self.elf), implementation],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def write_manifest(self, qbs: str, akv: str, akv_v2: str) -> None:
        (self.sim_dir / "simulator.conf").write_text(
            "schema_version=2\n"
            "sim_l2_bytes=1048576\n"
            f"qbs_enabled={qbs}\n"
            f"akv_enabled={akv}\n"
            f"akv_v2_enabled={akv_v2}\n",
            encoding="utf-8",
        )

    def test_schema2_manifest_accepts_matching_akv_v2(self) -> None:
        self.write_manifest("1", "1", "1")
        result = self.run_checker("akv_v2_prefill")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sim_akv_v2_enabled=1", result.stdout)
        self.assertIn("sim_capability_evidence=simulator_manifest", result.stdout)

    def test_schema2_manifest_rejects_disabled_akv_v2(self) -> None:
        self.write_manifest("1", "1", "0")
        result = self.run_checker("akv_v2_prefill")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not enable AKV-v2", result.stderr)

    def test_schema2_manifest_rejects_inconsistent_akv_v2(self) -> None:
        self.write_manifest("1", "0", "1")
        result = self.run_checker("akv_v2_prefill")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AKV-v2 requires AKV", result.stderr)

    def test_schema2_manifest_rejects_invalid_capability_value(self) -> None:
        self.write_manifest("1", "enabled", "1")
        result = self.run_checker("akv_v2_prefill")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid simulator capability value", result.stderr)

    def test_legacy_filelist_infers_capabilities(self) -> None:
        filelist = self.root / "filelist.f"
        filelist.write_text(
            "+define+SIM_L2_SIZE_BYTES=1048576\n"
            "+define+ARA_QBS_ENABLE=1\n"
            "+define+ARA_AKV_ENABLE=1\n"
            "+define+ARA_AKV_V2_ENABLE=1\n",
            encoding="utf-8",
        )
        (self.sim_dir / "comp.vcs.log").write_text(
            f"-f {filelist}\n", encoding="utf-8"
        )
        result = self.run_checker("akv_v2_prefill")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sim_capability_evidence=compile_filelist", result.stdout)
        self.assertIn("sim_l2_evidence=compile_filelist", result.stdout)


if __name__ == "__main__":
    unittest.main()
