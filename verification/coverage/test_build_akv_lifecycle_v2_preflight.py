"""Exact successor delta and immediate CSR-observation contract."""
import unittest
import build_akv_lifecycle_v2_preflight as b
from test_build_akv_lifecycle_preflight import LifecycleTest, NativeEncodingTest, SoftwareOutputTest


class CaptureContractTest(unittest.TestCase):
    def setUp(self):
        self.old=(b.first.ROOT/"apps/riscv-tests/isa/rv64uv/vakv_lifecycle_boundary.c").read_text()
        self.new=b.APP.read_text()

    def test_exact_minimal_successor(self):b.capture_contract(self.old,self.new)

    def test_pre_CSR_VSET_rejected(self):
        with self.assertRaises(ValueError):b.capture_contract(self.old,self.old)

    def test_missing_CSR_capture_rejected(self):
        with self.assertRaises(ValueError):b.capture_contract(self.old,self.new.replace("capture_csrs(p);",""))

    def test_changed_workload_rejected(self):
        with self.assertRaises(ValueError):b.capture_contract(self.old,self.new.replace("0x0405345b","0x0005345b"))

    def test_predecessor_seal_matches(self):
        self.assertEqual(b.first.sha(b.FIRST/"preflight-manifest.json"),b.FIRST_SEAL)


if __name__=="__main__":unittest.main()
