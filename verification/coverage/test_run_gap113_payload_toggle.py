import copy
import json
import unittest
import run_gap113_payload_toggle as tool


class Tests(unittest.TestCase):
    def setUp(self):self.pre=json.loads((tool.PRE/'preflight-manifest.json').read_bytes())

    def test_actual_preflight_contract(self):tool.validate(self.pre)

    def test_elf_scope_counts_budget_and_admission_drift(self):
        for key,value in [('binary','/tmp/other.elf'),('binary_sha256','0'*64),('commands',1),
                          ('host_negative_tests',0),('source_bytes',1),('budget_s',900),
                          ('coverage_admitted',True),('full_scalar_isa_verified',True)]:
            with self.subTest(key=key):
                p=copy.deepcopy(self.pre);p[key]=value
                with self.assertRaises(ValueError):tool.validate(p)

    def test_target_missing_rejected(self):
        self.pre['target']['serialized_zero_coordinates'].pop()
        with self.assertRaises(ValueError):tool.validate(self.pre)

    def test_existing_output_rejected_before_launch(self):
        with self.assertRaises(ValueError):tool.prepare(tool.PRE)


if __name__=='__main__':unittest.main()
