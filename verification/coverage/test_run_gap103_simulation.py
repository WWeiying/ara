from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import run_gap103_simulation as m


class RunnerTests(unittest.TestCase):
    def pre(self): return json.loads((m.PRE/"preflight-manifest.json").read_bytes())
    def targets(self): return json.loads((m.PRE/"target-before.json").read_bytes())

    def test_actual_frozen_preflight_and_targets(self):
        self.assertEqual(m.life.digest(m.PRE/"preflight-manifest.json"),m.PRE_SEAL)
        m.validate(self.pre()); m.validate_targets(self.targets())

    def test_wrong_case_base_or_oracle_rejected(self):
        for key,value in (("baseline_tests",718),("case","vgap102b_widen_acc_vstart"),
                          ("checks",723),("vcs_started",True)):
            pre=self.pre(); pre[key]=value
            with self.assertRaises(ValueError): m.validate(pre)
        pre=self.pre(); pre["validation"]["vstart"]=0
        with self.assertRaises(ValueError): m.validate(pre)

    def test_elf_expected_pin_not_overwritten(self):
        pre=self.pre(); pre["pins"][str(m.ELF)]="a"*64
        with self.assertRaises(ValueError): m.validate(pre)

    def test_missing_reference_or_host_pin_rejected(self):
        for name in ("spike.trace","compile-command.json","host.log"):
            pre=self.pre(); pre["pins"].pop(str(m.PRE/name))
            with self.assertRaises(ValueError): m.validate(pre)

    def test_compiled_raw_checksum_and_arm_rejected(self):
        for field,value in (("width",1214),("checksum","0"),("hit_before",True)):
            targets=self.targets(); targets["targets"][0][field]=value
            with self.assertRaises(ValueError): m.validate_targets(targets)
        targets=self.targets(); targets["targets"][0]["point"]["vector"]="1002"
        with self.assertRaises(ValueError): m.validate_targets(targets)

    def test_missing_or_reordered_target_rejected(self):
        targets=self.targets(); targets["targets"].pop()
        with self.assertRaises(ValueError): m.validate_targets(targets)
        targets=self.targets(); targets["targets"].reverse()
        with self.assertRaises(ValueError): m.validate_targets(targets)

    def test_exact_lifecycle_command(self):
        out=m.life.OUT/"gap103-test-not-created"
        command=m.command(out)
        self.assertEqual(command[0],str(m.life.IMAGE))
        self.assertEqual(command.count("+NO_FSDB"),1)
        self.assertIn("+PRELOAD="+str(m.ELF),command)
        self.assertIn("+COMMIT_TRACE="+str(out/"commit_trace.csv"),command)
        self.assertIn("+VECTOR_TRACE="+str(out/"vector_trace.csv"),command)
        self.assertIn(str(out/"code.vdb"),command)
        self.assertNotIn("+FSDB",command)

    def test_no_run_without_reviewed_seal(self):
        with patch.object(m.life,"run") as run:
            with self.assertRaises(SystemExit): m.main(["run","--output",str(m.life.OUT/"not-created")])
            run.assert_not_called()

    def test_conflicting_pin_rejected(self):
        with self.assertRaises(ValueError): m.life.merge_pins({"path":"a"*64},{"path":"b"*64})


if __name__ == "__main__": unittest.main()
