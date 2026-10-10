"""Strict reviewed single-run preparation; tests never invoke VCS."""
import copy
from pathlib import Path
import unittest

import run_akv_lifecycle_simulation as r


class LifecycleRunnerTest(unittest.TestCase):
    def setUp(self):
        self.pre=r.life.read_bound(r.PRE/"preflight-manifest.json",r.PRE_SEAL)
        self.target=r.life.read_bound(r.PRE/"target-before.json",self.pre["pins"][str(r.PRE/"target-before.json")])

    def test_actual_preflight_and_target(self):
        r.validate(self.pre,r.PRE);r.validate_target(self.target)

    def reject(self,key,value):
        self.pre[key]=value
        with self.assertRaises(ValueError):r.validate(self.pre,r.PRE)

    def test_no_fake_full_scalar(self):self.reject("full_scalar_independent_qualified",True)
    def test_no_fake_Spike_differential(self):self.reject("full_scalar_differential_qualified",True)
    def test_wrong_custom_byte_count(self):self.reject("native_expected_custom_write_bytes",388)
    def test_bool_command_count(self):self.reject("dut_expected_commands",True)
    def test_wrong_frame_count(self):self.reject("dut_expected_vrf_frames",4)
    def test_wrong_CSR_bytes(self):self.reject("dut_expected_CSR_bytes",192)

    def test_missing_trap_rejected(self):
        self.pre["dut_expected_traps"].pop()
        with self.assertRaises(ValueError):r.validate(self.pre,r.PRE)

    def test_wrong_trap_PC_or_cause_or_tval(self):
        for key in ("pc","cause","tval"):
            pre=copy.deepcopy(self.pre);pre["dut_expected_traps"][0][key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate(pre,r.PRE)

    def test_missing_input_pin_rejected(self):
        del self.pre["pins"][str(r.PRE/"input.elf")]
        with self.assertRaises(ValueError):r.validate(self.pre,r.PRE)

    def test_wrong_ELF_pin_rejected(self):
        self.pre["pins"][str(r.PRE/"input.elf")]='0'*64
        with self.assertRaises(ValueError):r.validate(self.pre,r.PRE)

    def test_pre_CSR_VSET_contract_rejected(self):
        self.target["command_return_CSR_capture_before_snapshot_VSET"]=False
        with self.assertRaises(ValueError):r.validate_target(self.target)

    def test_missing_or_changed_target_rejected(self):
        self.target["targets"].pop()
        with self.assertRaises(ValueError):r.validate_target(self.target)

    def test_hit_target_rejected(self):
        self.target["targets"][0]["baseline_hit"]=True
        with self.assertRaises(ValueError):r.validate_target(self.target)

    def test_wrong_compiled_coordinate_rejected(self):
        self.target["targets"][0]["point"]["vector"]="10"
        with self.assertRaises(ValueError):r.validate_target(self.target)

    def test_exact_native_command_no_software_or_FSDB(self):
        output=r.life.OUT/"not-launched-lifecycle"
        command=r.command(self.pre,output)
        self.assertEqual(command[0],str(r.life.IMAGE))
        self.assertIn("+PRELOAD="+str(r.PRE/"input.elf"),command)
        self.assertNotIn("+PRELOAD="+str(r.PRE/"software.elf"),command)
        self.assertIn("+NO_FSDB",command);self.assertIn("+AKV_PERF",command)
        self.assertIn("+COMMIT_TOHOST=80001000",command)

    def test_invalid_or_bool_budget_rejected(self):
        for budget in (True,0,299,301,900):
            with self.subTest(budget=budget),self.assertRaises(ValueError):
                r.prepare(r.PRE,r.PRE_SEAL,r.life.OUT/"not-launched-lifecycle",budget)

    def test_foreign_output_rejected(self):
        with self.assertRaises(ValueError):r.prepare(r.PRE,r.PRE_SEAL,Path("/tmp/foreign"),300)

    def test_foreign_preflight_rejected(self):
        with self.assertRaises(ValueError):r.prepare(r.PRE.parent/"foreign",r.PRE_SEAL,r.life.OUT/"unused",600)

    def test_bad_preflight_seal_rejected(self):
        with self.assertRaises(ValueError):r.prepare(r.PRE,'0'*64,r.life.OUT/"unused",600)


if __name__=="__main__":unittest.main()
