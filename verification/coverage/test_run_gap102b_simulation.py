import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_gap102b_simulation as m


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre=json.loads((m.PRE/"preflight-manifest.json").read_bytes())
        self.targets=json.loads((m.PRE/"target-before.json").read_bytes())

    def test_exact_sealed_contract(self):
        m.validate(self.pre);m.validate_targets(self.targets)

    def test_fixed_elf_not03_placeholder(self):
        self.assertEqual(m.ELF.parent,m.proof.PRE)
        self.pre["input_elf"]=str(m.PRE/"input.elf")
        with self.assertRaises(ValueError):m.validate(self.pre)

    def test_changed_elf_expected_pin(self):
        self.pre["pins"][str(m.ELF)]="0"*64
        with self.assertRaises(ValueError):m.validate(self.pre)

    def test_exact_nonzero_vstart_and_declared_bytes(self):
        for key,value in (("vstart",0),("active_result_bytes",516),("vector_declared_bytes",4),
                          ("declared_preserved_registers",[]),("illegal_traps",1)):
            bad=copy.deepcopy(self.pre);bad["validation"][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate(bad)

    def test_missing_qualified_oracle_pin(self):
        del self.pre["pins"][str(Path(m.proof.__file__).resolve())]
        with self.assertRaises(ValueError):m.validate(self.pre)

    def test_false_flags_type_strict(self):
        self.pre["vcs_started"]=0
        with self.assertRaises(ValueError):m.validate(self.pre)

    def test_exact_coordinate_not_root_line(self):
        for field,value in (("raw_index",128),("vector","1259")):
            bad=copy.deepcopy(self.targets);bad["targets"][0]["point"][field]=value
            with self.assertRaises(ValueError):m.validate_targets(bad)

    def test_parent_and_false_path_strict(self):
        point=self.targets["targets"][0]["point"]
        vector=list(point["native_vector"]["vector"]);vector[-1260]="0"
        point["native_vector"]["vector"]="".join(vector)
        with self.assertRaises(ValueError):m.validate_targets(self.targets)

    def test_no_extra_target(self):
        self.targets["targets"].append(copy.deepcopy(self.targets["targets"][0]))
        with self.assertRaises(ValueError):m.validate_targets(self.targets)

    def test_no_expected_pin_overwrite(self):
        with self.assertRaises(ValueError):m.life.merge_pins({"/tmp/fixed":"a"*64},{"/tmp/fixed":"b"*64})

    def test_fixed_command_and_no_fsdb(self):
        out=m.life.OUT/"gap102b-command-unit-only"
        cmd=m.command(out)
        self.assertIn("+NO_FSDB",cmd)
        self.assertIn("+PRELOAD="+str(m.ELF),cmd)
        self.assertIn("+COMMIT_TRACE="+str(out/"commit_trace.csv"),cmd)
        self.assertIn("+VECTOR_TRACE="+str(out/"vector_trace.csv"),cmd)
        self.assertEqual(cmd[cmd.index("-cm_dir")+1],str(out/"code.vdb"))
        self.assertEqual(cmd[0],str(m.life.IMAGE))

    def test_existing_foreign_path_no_launch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m.life,"run") as run:
            with self.assertRaises(ValueError):m.prepare(Path(tmp))
            run.assert_not_called()

    def test_no_unsealed_run(self):
        with patch.object(m.life,"run") as run,patch.object(m,"prepare") as prepare:
            with self.assertRaises(SystemExit):m.main(["run","--output",str(m.life.OUT/"gap102b-test-only")])
            prepare.assert_not_called();run.assert_not_called()


if __name__=="__main__":unittest.main()
