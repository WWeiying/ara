import unittest
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RtlContractTests(unittest.TestCase):
    def test_real_boundary_testcase_selects_matching_elf(self):
        result = subprocess.run(
            ["make", "-n", "real-ara-contract-run",
             "REAL_CONTRACT_TESTCASE=rv64uv-ara-vadd"],
            cwd=ROOT / "verification", text=True, capture_output=True, check=True,
        )
        self.assertIn("apps/bin/rv64uv-ara-vadd", result.stdout)
        self.assertIn("rv64uv-ara-vadd.log", result.stdout)
        self.assertNotIn("apps/bin/rv64uv-ara-vfredmax_boundary", result.stdout)

    def test_diagnostic_order_probe_is_not_in_normal_rtl(self):
        sources = list((ROOT / "hardware").rglob("*.sv"))
        residual = []
        for path in sources:
            text = path.read_text(encoding="utf-8", errors="replace")
            for marker in ("ARA_TRACE_ORDER", "ORDER_TRACE"):
                if marker in text:
                    residual.append(f"{path}:{marker}")
        self.assertEqual([], residual)

    def test_uvm_smoke_waits_for_transaction_completion(self):
        source = (ROOT / "verification/uvm/ara_cvxif_uvm_pkg.sv").read_text()
        tb = (ROOT / "verification/uvm/ara_cvxif_smoke_tb.sv").read_text()
        self.assertIn("phase.raise_objection", source)
        self.assertIn("vif.smoke_done", source)
        self.assertIn("cvxif.smoke_done = 1'b1", tb)

    def test_real_ara_boundary_monitor_is_bound_to_actual_struct_fields(self):
        source = (ROOT / "verification/uvm/ara_acc_contract_monitor.sv").read_text()
        self.assertIn("bind ara_system ara_acc_contract_monitor", source)
        self.assertIn("acc_req.acc_req.req_valid", source)
        self.assertIn("acc_resp.acc_resp.req_ready", source)
        self.assertIn("acc_resp.acc_resp.resp_valid", source)
        self.assertIn("acc_req.acc_req.resp_ready", source)
        self.assertIn("acc_req.acc_req.trans_id", source)
        self.assertIn("acc_resp.acc_resp.exception.valid", source)
        self.assertIn("acc_req.acc_mmu_resp.acc_mmu_valid", source)
        self.assertIn("p_request_stable_until_ready", source)
        self.assertIn("p_response_stable_until_ready", source)

    def test_real_boundary_compile_is_isolated_from_normal_hardware_compile(self):
        makefile = (ROOT / "hardware/Makefile").read_text()
        verification_makefile = (ROOT / "verification/Makefile").read_text()
        self.assertIn("verify_extra_sources", makefile)
        self.assertIn("real-ara-contract-compile", verification_makefile)
        self.assertIn("real-ara-contract-smoke", verification_makefile)
        self.assertIn("-m ara_verify.contract", verification_makefile)
        self.assertIn("contract-selftest:", verification_makefile)
        self.assertIn("buildpath=$(REAL_CONTRACT_OUT)/hardware-build", verification_makefile)

    def test_fp_reduction_neutral_encoding_is_not_narrowing(self):
        source = (ROOT / "hardware/src/lane/vmfpu.sv").read_text()
        self.assertIn(
            "function automatic logic narrowing(resize_e resize, ara_op_e op);",
            source,
        )
        self.assertIn(
            "resize == CVT_NARROW && !(op inside {[VFREDUSUM:VFWREDOSUM]})",
            source,
        )
        self.assertNotIn("narrowing(vinsn_issue_q.cvt_resize)", source)
        self.assertNotIn("narrowing(vinsn_processing_q.cvt_resize)", source)

    def test_vector_configuration_does_not_discard_reserved_bits(self):
        # Source guards complement the actual SoC test; not an ISA proof.
        source = (ROOT / "hardware/src/ara_dispatcher.sv").read_text()
        self.assertIn("vill  : |xlen[CVA6Cfg.XLEN-1:8]", source)
        self.assertIn("vtype_xlen(xlen_t'(acc_req_i.rs2))", source)
        self.assertNotIn("vtype_xlen(xlen_t'(acc_req_i.rs2[7:0]))", source)
        self.assertIn("if (csr_vtype_d.vill ||", source)

    def test_vfredmax_boundary_regression_is_in_the_directed_source(self):
        source = (ROOT / "apps/riscv-tests/isa/rv64uv/vfredmax.c").read_text()
        self.assertIn("void TEST_CASE6(void)", source)
        self.assertIn("0xC1700000, 0x41700000", source)
        self.assertIn("0xFF800000", source)
        self.assertIn("VCMP_U32(18, v1, 0x41700000)", source)

        focused = (ROOT / "apps/riscv-tests/isa/rv64uv/vfredmax_boundary.c").read_text()
        self.assertIn('asm volatile("vfredmax.vs v1, v2, v3")', focused)
        self.assertIn("VCMP_U32(1, v1, 0x41700000)", focused)


if __name__ == "__main__":
    unittest.main()
