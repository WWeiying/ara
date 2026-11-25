"""Offline CLI regressions using immutable good and failing Resident runs."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent / "out"
OLD = Path("/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out")
ELF = {
    "qk": OLD / "resident_qk_boundary_build_20261110_01/resident_qk_boundary.elf",
    "pv": OLD / "resident_pv_soc_boundary_build_20261109_02/resident_pv_boundary.elf",
}
GOLD = {
    "qk": OLD / "stage3_qk_boundary_v2_20261110_01/work/run.vcs.log",
    "pv": OLD / "stage3_pv_boundary_20261110_01/work/run.vcs.log",
}


class OracleTest(unittest.TestCase):
    def run_check(self, kind, path, expected_rc, elf=None):
        result = subprocess.run([sys.executable, "-IB", str(HERE / "resident_firmware_oracle_v1.py"),
                                 kind, "--elf", str(elf or ELF[kind]), "--log", str(path)],
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected_rc, (result.stdout, result.stderr))
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "FAIL" if expected_rc else "PASS")
        return report

    def test_gold(self):
        for kind, attempts, records in (("qk", 35, 76), ("pv", 33, 71)):
            with self.subTest(kind=kind):
                r = self.run_check(kind, GOLD[kind], 0)
                self.assertEqual((r["attempts"], r["boundary_records"]), (attempts, records))
                self.assertFalse(r["trace_checked"] or r["protocol_checked"])

    def test_observed_failures(self):
        qk = LOCAL / "ex-fp-credit-20261122-02"
        r = self.run_check("qk", qk / "soc/reference/resident_qk/run.log", 1, qk / "elf/resident_qk")
        self.assertIn("trap CSR", r["error"])
        r = self.run_check("pv", OLD / "resident_pv_soc_boundary_vcs_20261109_01/work/run.vcs.log", 1)
        self.assertIn("trap CSR", r["error"])

    def test_same_bad_bits_would_pair(self):
        with tempfile.TemporaryDirectory(prefix="resident_firmware_test_", dir=LOCAL) as tmp:
            for kind in ELF:
                with self.subTest(kind=kind):
                    original = GOLD[kind].read_text()
                    changed, n = re.subn(r"(kind=result bits=)([0-9a-f])",
                                         lambda m: m[1] + format(int(m[2], 16) ^ 1, "x"),
                                         original, count=1)
                    self.assertEqual(n, 1)
                    path = Path(tmp) / "mutated.log"
                    path.write_text(changed)
                    self.assertIn("mismatch", self.run_check(kind, path, 1)["error"])

    def test_golden_csr_field_not_covered_by_numerical(self):
        with tempfile.TemporaryDirectory(prefix="resident_firmware_test_", dir=LOCAL) as tmp:
            path = Path(tmp) / "csr.log"
            original = GOLD["qk"].read_text()
            changed = original.replace("before_mstatus=8000000a00006680",
                                       "before_mstatus=8000000a00004680", 1)
            self.assertNotEqual(original, changed)
            path.write_text(changed)
            self.assertIn("Golden boundary record", self.run_check("qk", path, 1)["error"])

    def test_wrong_elf(self):
        self.assertIn("Pin mismatch", self.run_check("qk", GOLD["qk"], 1, ELF["pv"])["error"])

    def test_truncated_after_done(self):
        with tempfile.TemporaryDirectory(prefix="resident_firmware_test_", dir=LOCAL) as tmp:
            path = Path(tmp) / "partial.log"
            path.write_text(GOLD["pv"].read_text().split("Core Test *** SUCCESS")[0])
            self.assertIn("tohost exit", self.run_check("pv", path, 1)["error"])


if __name__ == "__main__":
    unittest.main()
