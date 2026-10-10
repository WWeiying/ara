import copy
import json
from pathlib import Path
import unittest

import run_akv_column_boundary_v2_simulation as r

PRE = r.life.OUT / "akv-column-boundary-v2-preflight-717-20261006-01"
PRE_SHA = "629dce5e446f002cf5ea7ec84895ee923b3a8c12fcf1df298f7d15253f89677d"


class RunnerSuccessorTest(unittest.TestCase):
    def setUp(self):
        self.pre = r.life.read_bound(PRE / "preflight-manifest.json", PRE_SHA)

    def reject(self, key, value):
        self.pre[key] = value
        with self.assertRaises(ValueError): r.validate(self.pre, PRE)

    def test_actual_sealed_preflight_positive(self):
        r.validate(self.pre, PRE)

    def test_reject_old_zero_fill_contract(self): self.reject("native_expected_custom_write_bytes", 640)
    def test_reject_inactive_not_preserved(self): self.reject("inactive_tail_preserved", False)
    def test_reject_unobserved_CSR_claim(self): self.reject("actual_CSR_snapshots_required", False)
    def test_reject_old_budget(self): self.reject("old_image_timeout_s", 300)
    def test_reject_bool_command_count(self): self.reject("dut_expected_commands", True)
    def test_reject_wrong_trap_PC(self): self.reject("dut_expected_trap_pc", self.pre["dut_expected_trap_pc"]+4)
    def test_reject_native_spike_claim(self): self.reject("spike_native_custom_model_available", True)
    def test_reject_full_scalar_qualification_claim(self): self.reject("full_scalar_differential_qualified", True)

    def test_reject_missing_input_pin(self):
        self.pre["pins"].pop(str(PRE / "input.elf"))
        with self.assertRaises(ValueError): r.validate(self.pre, PRE)

    def test_exact_900s_native_command(self):
        out = r.life.OUT / "unlaunched-v2"
        command = r.command(self.pre, out)
        self.assertIn("+PRELOAD="+str(PRE / "input.elf"), command)
        self.assertNotIn("+PRELOAD="+str(PRE / "software.elf"), command)
        self.assertIn("+TESTCASE=vakv_column_boundary_v2", command)
        self.assertIn("+NO_FSDB", command)
        self.assertIn("+AKV_PERF", command)
        self.assertIn("+COMMIT_TOHOST=80001000", command)

    def test_reject_foreign_output(self):
        with self.assertRaises(ValueError): r.prepare(PRE, PRE_SHA, Path("/tmp/foreign"))


if __name__ == "__main__":
    unittest.main()
