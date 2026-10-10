"""Focused checks for paired RVV/QBS cycle-accounting evidence."""

import unittest
import tempfile
from pathlib import Path

from compare_real_dut_pair import case_summary, custom_allocations, image_components, phase_gap


class PhaseGapTest(unittest.TestCase):
    def test_case_summary_accepts_missing_optional_capture_root(self) -> None:
        self.assertEqual(case_summary({"weight_type": "q4_K", "k": 1536,
                                       "rows": 256, "case_id": "q4"}),
                         {"weight_type": "q4_K", "k": 1536, "rows": 256})

    def test_standard_rvv_rejects_all_custom2_allocations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "vector.csv"
            trace.write_text(
                "cycle,event,arch_seq,vid,lane,source,insn\n"
                "1,alloc,1,0,0,0,00b5045b\n"
                "2,alloc,2,1,0,0,00d5045b\n"
                "3,done,2,1,0,0,00d5045b\n"
                "4,alloc,3,2,0,0,5e003857\n", encoding="utf-8"
            )
            self.assertEqual(custom_allocations(trace), (1, 2))

    def test_phase_control_cycles_are_accounted_separately(self) -> None:
        issues = []
        record = {"compute_cycles": "173026", "quantize_cycles": "6732",
                  "pack_cycles": "0", "matmul_cycles": "166250"}
        self.assertEqual(phase_gap(record, "RVV", issues), 44)
        self.assertEqual(issues, [])

    def test_stage_cycles_exceeding_total_fail(self) -> None:
        issues = []
        record = {"compute_cycles": "10", "quantize_cycles": "8",
                  "pack_cycles": "0", "matmul_cycles": "3"}
        self.assertIsNone(phase_gap(record, "RVV", issues))
        self.assertTrue(issues)

    def test_missing_stage_fails(self) -> None:
        issues = []
        self.assertIsNone(phase_gap({"compute_cycles": "10"}, "RVV", issues))
        self.assertTrue(issues)

    def test_vcs_image_components_exclude_runner_and_elf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "INPUT_SHA256SUMS"
            manifest.write_text(
                f"{'a' * 64}  /vcs/simv\n"
                f"{'b' * 64}  /vcs/simulator.conf\n"
                f"{'c' * 64}  /vcs/simv.daidir/module.so\n"
                f"{'d' * 64}  /verification/uvm/run_real_dut_case.sh\n"
                f"{'e' * 64}  work/input.elf\n", encoding="utf-8")
            self.assertEqual(image_components(manifest), {
                "simv": "a" * 64,
                "simulator.conf": "b" * 64,
                "simv.daidir/module.so": "c" * 64,
            })


if __name__ == "__main__":
    unittest.main()
