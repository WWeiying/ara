import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class UvmBuildContractTests(unittest.TestCase):
    def test_real_dut_uvm_requires_bind_sources(self):
        command = ["make", "-C", str(ROOT / "hardware"), "-n", "compile",
                   "verify_uvm_cvxif=1", "no_fsdb=1"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        for source in ("ara_cvxif_if.sv", "ara_cvxif_uvm_pkg.sv",
                       "ara_acc_contract_monitor.sv", "ara_cvxif_dut_bind.sv"):
            self.assertIn(source, result.stderr)
