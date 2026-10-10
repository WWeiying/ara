import copy
import json
import unittest
import run_gap113_payload_full8 as r


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=r.life.read_bound(r.PRE/'preflight-manifest.json',r.SEAL)

    def test_actual_contract(self):
        r.validate(self.pre)
        r.life.check(r.life.merge_pins(self.pre['input_pins'],self.pre['output_pins']))

    def test_contract_negative(self):
        for key,value in [('m',5),('n',7),('budget_s',900),('full_vrf_words',1024),
                          ('source_guard_bytes',0),('csr_words',12),('host_negative_tests',0),
                          ('weight_high_mask_byte_encodings',2),('activation_groups_per_command',64),
                          ('vcs_launched',True),('binary_sha256','0'*64)]:
            bad=copy.deepcopy(self.pre);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate(bad)

    def test_site_negative(self):
        for sites in ([],self.pre['sites'][:1],[dict(pc=1,word=0x08b5045b)]*2):
            bad=copy.deepcopy(self.pre);bad['sites']=sites
            with self.assertRaises(ValueError):r.validate(bad)


if __name__=='__main__':unittest.main()
