import copy
import json
import unittest

import prepare_akv_lifecycle_candidate_723 as candidate


def bitmap(tests, bit=0):
    scope="ara_tb.dut.i_ara_soc.i_system"
    return dict(design={"shape":"a"*64},tests=tests,input_hashes={tests[0]+"/metric.xml":"a"*64},metrics={
        m:{scope:dict(width=2,checksum="123",bits=hex(bit))} for m in candidate.bitmap.METRICS})


class CandidateTests(unittest.TestCase):
    def before(self):return bitmap(["/historical/test%d.vdb" % i for i in range(723)])
    def single(self):return bitmap([str(candidate.RUN/"code.vdb")],1)

    def test_positive_exact_population(self):
        before=self.before();proposed,delta=candidate.population(before,self.single())
        self.assertEqual(proposed["tests"][:-1],before["tests"])
        self.assertEqual(len(proposed["tests"]),724)
        self.assertEqual(sum(delta["metrics"].values()),4)
        self.assertEqual(before["metrics"]["cond"]["ara_tb.dut.i_ara_soc.i_system"]["bits"],"0x0")

    def test_zero_gain_rejected(self):
        with self.assertRaises(ValueError):candidate.population(self.before(),bitmap([str(candidate.RUN/"code.vdb")]))

    def test_wrong_baseline_population(self):
        before=self.before();before["tests"].pop()
        with self.assertRaises(ValueError):candidate.population(before,self.single())

    def test_duplicate_baseline_member(self):
        before=self.before();before["tests"][-1]=before["tests"][0]
        with self.assertRaises(ValueError):candidate.population(before,self.single())

    def test_duplicate_new_member(self):
        before=self.before();before["tests"][-1]=str(candidate.RUN/"code.vdb")
        with self.assertRaises(ValueError):candidate.population(before,self.single())

    def test_foreign_singleton(self):
        with self.assertRaises(ValueError):candidate.population(self.before(),bitmap(["/failed/other.vdb"],1))

    def test_shape_drift(self):
        single=self.single();single["metrics"]["cond"]["ara_tb.dut.i_ara_soc.i_system"]["checksum"]="456"
        with self.assertRaises(ValueError):candidate.population(self.before(),single)

    def test_design_drift(self):
        single=self.single();single["design"]["shape"]="b"*64
        with self.assertRaises(ValueError):candidate.population(self.before(),single)

    def test_metric_missing(self):
        single=self.single();single["metrics"].pop("fsm")
        with self.assertRaises(ValueError):candidate.population(self.before(),single)

    def test_bitmap_overflow(self):
        single=self.single();single["metrics"]["cond"]["ara_tb.dut.i_ara_soc.i_system"]["bits"]="0x4"
        with self.assertRaises(ValueError):candidate.population(self.before(),single)

    def test_boolean_width(self):
        single=self.single();single["metrics"]["cond"]["ara_tb.dut.i_ara_soc.i_system"]["width"]=True
        with self.assertRaises(ValueError):candidate.population(self.before(),single)

    def test_bitmap_input_hash_conflict(self):
        before=self.before();single=self.single()
        before["input_hashes"]={"/same":"a"*64};single["input_hashes"]={"/same":"b"*64}
        with self.assertRaises(ValueError):candidate.population(before,single)

    def test_duplicate_ELF(self):
        with self.assertRaises(ValueError):candidate.unique_elf("a"*64,{"/previous.elf":"a"*64})

    def test_distinct_ELF(self):candidate.unique_elf("b"*64,{"/previous.elf":"a"*64})

    def read(self,name):return json.loads((candidate.QUALIFIED/name).read_text())

    def qualified(self,**updates):
        args=dict(seal=self.read("qualification-seal.json"),scalar=self.read("scalar-qualification.json"),
                  vector=self.read("native-vector.json"),contract=self.read("contract.json"),
                  compiled=self.read("compiled-source-binding.json"))
        args.update(updates);candidate.qualification_contract(**args)

    def test_actual_sealed_qualification_scope(self):self.qualified()

    def test_missing_scalar_evidence(self):
        scalar=self.read("scalar-qualification.json");scalar.pop("full_scalar_independent_qualified")
        with self.assertRaises(ValueError):self.qualified(scalar=scalar)

    def test_scalar_skip_rejected(self):
        scalar=self.read("scalar-qualification.json");scalar["skipped_retirements"]=1
        with self.assertRaises(ValueError):self.qualified(scalar=scalar)

    def test_boolean_retirement_count(self):
        scalar=self.read("scalar-qualification.json");scalar["matched_retirements"]=True
        with self.assertRaises(ValueError):self.qualified(scalar=scalar)

    def test_missing_v2_test_pin(self):
        seal=self.read("qualification-seal.json")
        path=str(candidate.qualification.required_tests()[1]);seal["input_pins"].pop(path)
        with self.assertRaises(ValueError):self.qualified(seal=seal)

    def test_rejected_vector_write(self):
        vector=self.read("native-vector.json");vector["rejected_write_bytes"]=2
        with self.assertRaises(ValueError):self.qualified(vector=vector)

    def test_terminal_stall_rejected(self):
        contract=self.read("contract.json");contract["resp_stalled"]=1
        with self.assertRaises(ValueError):self.qualified(contract=contract)

    def test_wrong_compiled_checksum(self):
        compiled=self.read("compiled-source-binding.json");compiled["condition_checksum"]="0"
        with self.assertRaises(ValueError):self.qualified(compiled=compiled)

    def baseline(self,**updates):
        manifest=json.loads((candidate.BASE/"admission-manifest.json").read_text())
        status=json.loads((candidate.BASE/"status.json").read_text())
        before=json.loads((candidate.BASE/"combined-bits.json").read_text())
        parent=json.loads((candidate.PARENT/"combined-bits.json").read_text())
        r1=json.loads((candidate.R1/"single-raw-bits.json").read_text())
        args=dict(manifest=manifest,status=status,before=before,parent=parent,r1=r1,
                  ledger=(candidate.BASE/"combined-inputs.txt").read_text().splitlines())
        args.update(updates);candidate.baseline_contract(**args)

    def test_actual_723_ancestry_and_OR(self):self.baseline()

    def test_nonPASS_baseline_rejected(self):
        status=json.loads((candidate.BASE/"status.json").read_text());status["status"]="FAIL"
        with self.assertRaises(ValueError):self.baseline(status=status)

    def test_wrong_parent_seal(self):
        manifest=json.loads((candidate.BASE/"admission-manifest.json").read_text());manifest["baseline_seal"]="0"*64
        with self.assertRaises(ValueError):self.baseline(manifest=manifest)

    def test_ordered_ledger_alias_rejected(self):
        ledger=(candidate.BASE/"combined-inputs.txt").read_text().splitlines();ledger[0]="/tmp/design.vdb"
        with self.assertRaises(ValueError):self.baseline(ledger=ledger)

    def test_prefix_reorder_rejected(self):
        before=json.loads((candidate.BASE/"combined-bits.json").read_text())
        before["tests"][0],before["tests"][1]=before["tests"][1],before["tests"][0]
        with self.assertRaises(ValueError):self.baseline(before=before)


if __name__ == "__main__":unittest.main()
