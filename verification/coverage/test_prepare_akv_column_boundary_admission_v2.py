"""Fail-closed scalar/native evidence gates; no aggregate admission in tests."""
import copy
import json
import unittest

import prepare_akv_column_boundary_admission_v2 as a


class QualificationGateTest(unittest.TestCase):
    def setUp(self):
        def read(name):
            return json.loads((a.QUALIFICATION/name).read_text())
        self.result=read("scalar-qualification.json")
        self.contract=read("source-contract.json")
        self.effects=read("independent-native-byte-binding.json")
        self.ledger=read("independent-custom-ledger.json")
        self.seal=read("qualification-seal.json")
        self.symbols=dict(boundary_bad=self.result["independently_derived_traps"][0]["pc"],
                          boundary_handler=self.result["independently_derived_traps"][0]["handler"])

    def validate(self):
        a.validate_scalar(self.result,self.contract,self.effects,self.ledger,self.symbols)

    def test_exact_sealed_qualification_accepted(self):
        a.life.read_bound(a.QUALIFICATION/"qualification-seal.json",a.QUALIFICATION_SEAL)
        a.life.check(self.seal["output_pins"])
        self.validate()

    def test_scalar_not_qualified_rejected(self):
        self.result["full_scalar_independent_qualified"]=False
        with self.assertRaises(ValueError):self.validate()

    def test_signature_only_partial_rejected(self):
        self.result["matched_retirements"]=1
        with self.assertRaises(ValueError):self.validate()

    def test_unknown_skipped_mismatch_rejected(self):
        for field in ("skipped_retirements","unknown_state_reads","mismatches"):
            with self.subTest(field=field):
                old=self.result[field];self.result[field]=1
                with self.assertRaises(ValueError):self.validate()
                self.result[field]=old

    def test_bool_cannot_substitute_counter(self):
        self.result["mismatches"]=False
        with self.assertRaises(ValueError):self.validate()

    def test_missing_scalar_field_rejected(self):
        del self.result["full_scalar_independent_qualified"]
        with self.assertRaises((ValueError,KeyError)):self.validate()

    def test_false_Spike_claim_rejected(self):
        self.result["full_scalar_differential_qualified"]=True
        with self.assertRaises(ValueError):self.validate()

    def test_wrong_trap_rejected(self):
        self.result["independently_derived_traps"][0]["tval"]=1
        with self.assertRaises(ValueError):self.validate()

    def test_missing_reset_contract_rejected(self):
        self.contract["reset_GPRs_all_zero"]=False
        with self.assertRaises(ValueError):self.validate()

    def test_missing_native_byte_binding_rejected(self):
        self.effects["matched_custom_bytes"]=387
        with self.assertRaises(ValueError):self.validate()

    def test_partial_custom_ledger_rejected(self):
        self.ledger.pop()
        with self.assertRaises(ValueError):self.validate()

    def test_missing_each_scalar_output_rejected(self):
        for name in a.QUAL_FILES:
            seal=copy.deepcopy(self.seal);del seal["output_pins"][str(a.QUALIFICATION/name)]
            with self.subTest(name=name),self.assertRaises(ValueError):a.bind_qualification(seal,{})

    def test_foreign_scalar_output_rejected(self):
        self.seal["output_pins"][str(a.life.OUT/"foreign.json")]='0'*64
        with self.assertRaises(ValueError):a.bind_qualification(self.seal,{})

    def test_wrong_candidate_binding_rejected(self):
        self.seal["input_pins"][str(a.old.r.CANDIDATE/"candidate-seal.json")]='0'*64
        with self.assertRaises(ValueError):a.bind_qualification(self.seal,{})

    def test_missing_run_binding_rejected(self):
        del self.seal["input_pins"][str(a.oracle.native.RUN/"manifest.json")]
        with self.assertRaises(ValueError):a.bind_qualification(self.seal,{})

    def test_conflicting_shared_pin_rejected(self):
        path=next(iter(self.seal["input_pins"]))
        with self.assertRaises(ValueError):a.bind_qualification(self.seal,{path:'0'*64})

    def test_scalar_seal_tamper_rejected(self):
        with self.assertRaises(ValueError):
            a.life.read_bound(a.QUALIFICATION/"qualification-seal.json",'0'*64)

    def test_new_baseline_requires_rebind(self):
        with self.assertRaisesRegex(ValueError,"fresh ancestry/delta"):
            a.evaluate('0'*64)

    def test_existing_output_rejected(self):
        with self.assertRaises(ValueError):a.fresh_output(a.QUALIFICATION)


if __name__ == "__main__":
    unittest.main()
