import copy
import unittest
from unittest.mock import patch

import run_valu_restart783 as r


class RuntimeTests(unittest.TestCase):
    def record(self):
        return dict(case=r.CASE,output=str(r.OUT),timeout_s=900,systemd_runtime_max_s=960,
            command=r.command(r.OUT),preflight_seal=r.PRE_SHA,baseline_seal=r.gold.BASE_SHA,
            coverage_admitted=False,automatic_retry=False,service=r.SERVICE,environment=r.environment())

    def test_command(self):
        c=r.command(r.OUT)
        self.assertEqual(c[0],str(r.life.IMAGE))
        self.assertEqual(c.count('+COMMIT_TOHOST=80001000'),1)
        self.assertIn('+NO_FSDB',c)
        self.assertNotIn('-ucli',c)
        self.assertIn('+PRELOAD='+str(r.gold.OUT/'input.elf'),c)

    def test_contract(self):
        self.assertEqual(r.validate(self.record()),r.OUT)
        for key,value in [('timeout_s',True),('timeout_s',600),('systemd_runtime_max_s',900),
            ('baseline_seal','foreign'),('automatic_retry',True),('service','unowned')]:
            q=self.record();q[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(Exception):r.validate(q)

    def test_absolute_environment(self):
        e=r.environment()
        self.assertTrue(e['VCS_HOME'].startswith('/'))
        self.assertTrue(all(p.startswith('/') for p in e['LD_LIBRARY_PATH'].split(':')))
        self.assertNotIn('',e['LD_LIBRARY_PATH'].split(':'))

    def test_bound_preflight(self):
        q=r.life.read_bound(r.PRE,r.PRE_SHA);r.life.check(q['pins'])
        self.assertEqual(q['counts']['matched_instructions'],170167)
        self.assertEqual(q['software_checks'],13144)
        self.assertEqual(q['baseline']['population'],783)
        self.assertEqual(q['baseline']['remaining_candidate_positions'],422)
        self.assertFalse(q['VCS_launched'])

    def test_frozen66(self):
        q=r.life.read_bound(r.life.PLAN,r.life.PLAN_SEAL)
        self.assertEqual(len(q['image']),66)
        self.assertEqual(q['image'][str(r.life.IMAGE)],r.frozen.IMAGE_SEAL)

    def test_bad_command(self):
        q=self.record();q['command']=q['command'][:-1]
        with self.assertRaises(Exception):r.validate(q)


if __name__=='__main__':unittest.main()
