import copy
import json
import unittest
import run_qbs_payload_phase763 as r


class TestRunner(unittest.TestCase):
    def record(self):return json.loads((r.PRE/'preflight-manifest.json').read_bytes())
    def test_actual_sealed_preflight(self):
        self.assertEqual(r.life.digest(r.PRE/'preflight-manifest.json'),r.SEAL)
        r.validate(self.record())
    def test_phase_drift(self):
        p=self.record();p['activation_skews']=[4,4]
        with self.assertRaises(ValueError):r.validate(p)
    def test_elf_drift(self):
        p=self.record();p['binary_sha256']='0'*64
        with self.assertRaises(ValueError):r.validate(p)
    def test_budget_bool_and_site(self):
        for key,value in [('budget_s',601),('host_checks',True),('commands',3)]:
            p=self.record();p[key]=value
            with self.assertRaises(ValueError):r.validate(p)
        p=self.record();p['sites'][0]['word']=0
        with self.assertRaises(ValueError):r.validate(p)


if __name__=='__main__':unittest.main()
