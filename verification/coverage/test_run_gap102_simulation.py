import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_gap102_simulation as m


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.PRE / "preflight-manifest.json").read_bytes())
        self.targets = json.loads((m.PRE / "target-before.json").read_bytes())

    def test_exact_contract(self):
        m.validate(self.pre)
        m.validate_targets(self.targets)

    def test_elf_not_replaceable(self):
        self.pre["pins"][str(m.PRE / "input.elf")]="0"*64
        with self.assertRaisesRegex(ValueError,"ELF"):
            m.validate(self.pre)

    def test_wrong_vl_or_trap_rejected(self):
        for field,value in (("vl",79),("illegal_traps",1),("active_result_bytes",512)):
            pre=copy.deepcopy(self.pre);pre["validation"][field]=value
            with self.assertRaisesRegex(ValueError,"oracle"):
                m.validate(pre)

    def test_missing_input_pin(self):
        del self.pre["pins"][str(m.PRE / "spike.trace")]
        with self.assertRaisesRegex(ValueError,"Unpinned"):
            m.validate(self.pre)

    def test_duplicate_target(self):
        self.targets["targets"].append(copy.deepcopy(self.targets["targets"][0]))
        with self.assertRaisesRegex(ValueError,"population"):
            m.validate_targets(self.targets)

    def test_wrong_native_coordinate(self):
        self.targets["targets"][0]["point"]["vector"]="1259"
        with self.assertRaisesRegex(ValueError,"identity"):
            m.validate_targets(self.targets)

    def test_wrong_zero_based_path(self):
        point=self.targets["targets"][0]["point"]
        vector=list(point["native_vector"]["vector"]);vector[-1260]="0"
        point["native_vector"]["vector"]="".join(vector)
        with self.assertRaisesRegex(ValueError,"false boundary"):
            m.validate_targets(self.targets)

    def test_wrong_parent_not_root_line(self):
        point=self.targets["targets"][0]["point"]
        next(e for e in point["expressions"] if e["id"]=="5843")["parent_bit"]="1"
        with self.assertRaisesRegex(ValueError,"leaf/parent"):
            m.validate_targets(self.targets)

    def test_expected_pin_conflict(self):
        with self.assertRaisesRegex(ValueError,"Conflicting"):
            m.life.merge_pins({"/tmp/fixed":"a"*64},{"/tmp/fixed":"b"*64})

    def test_exact_command(self):
        out=m.life.OUT/"gap102-test-command-only"
        command=m.command(out)
        self.assertEqual(command[0],str(m.life.IMAGE))
        self.assertIn("+NO_FSDB",command)
        self.assertIn("+PRELOAD="+str(m.PRE/"input.elf"),command)
        self.assertIn("+COMMIT_TRACE="+str(out/"commit_trace.csv"),command)
        self.assertIn("+VECTOR_TRACE="+str(out/"vector_trace.csv"),command)
        self.assertEqual(command.count("-cm_dir"),1)
        self.assertEqual(command[command.index("-cm_dir")+1],str(out/"code.vdb"))

    def test_existing_output_rejected_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m.life,"run") as run:
            with self.assertRaisesRegex(ValueError,"Fresh independent"):
                m.prepare(Path(tmp))
            run.assert_not_called()

    def test_no_implicit_run_without_external_seal(self):
        with patch.object(m.life,"run") as run,patch.object(m,"prepare") as prepare:
            with self.assertRaises(SystemExit):
                m.main(["run","--output",str(m.life.OUT/"gap102-test-only")])
            prepare.assert_not_called();run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
