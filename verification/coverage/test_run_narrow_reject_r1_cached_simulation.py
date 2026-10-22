"""Cached runner command and rejection gates; never call run()."""
import copy
import json
import os
from pathlib import Path
import unittest

import run_narrow_reject_r1_cached_simulation as r


class CommandTests(unittest.TestCase):
    def test_1800_wall_budget(self):self.assertEqual(r.BUDGET,1800)
    def test_frozen_old_image(self):self.assertEqual(r.command(r.life.OUT/'unused-r1-test')[0],str(r.life.IMAGE))
    def test_single_cached_case(self):
        c=r.command(r.life.OUT/'unused-r1-test')
        self.assertIn('+TESTCASE=vnarrow_reject_r1_matrix_cached',c)
        self.assertEqual(sum(x.startswith('+PRELOAD=') for x in c),1)
    def test_no_waveform_DVE(self):
        c=r.command(r.life.OUT/'unused-r1-test');self.assertIn('+NO_FSDB',c)
        self.assertNotIn('dve',' '.join(c).lower())


@unittest.skipUnless(os.environ.get('R1_CACHED_PREFLIGHT'),'Set actual cached preflight')
class ActualContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=json.loads((Path(os.environ['R1_CACHED_PREFLIGHT'])/'preflight-manifest.json').read_text())

    def test_actual_contract(self):r.validate(self.pre)
    def test_old_heavy_case_rejected(self):
        pre=copy.deepcopy(self.pre);pre['case']='vnarrow_reject_r1_matrix'
        with self.assertRaises(ValueError):r.validate(pre)
    def test_deleted_snapshot_rejected(self):
        pre=copy.deepcopy(self.pre);pre['validation']['observed_vrf_bytes']-=4096
        with self.assertRaises(ValueError):r.validate(pre)
    def test_deleted_trap_rejected(self):
        pre=copy.deepcopy(self.pre);pre['validation']['illegal_traps']=23
        with self.assertRaises(ValueError):r.validate(pre)
    def test_deleted_check_rejected(self):
        pre=copy.deepcopy(self.pre);pre['validation']['checks']=15488
        with self.assertRaises(ValueError):r.validate(pre)
    def test_native_target_drift_rejected(self):
        pre=copy.deepcopy(self.pre);pre['targets'][0]['point']['raw_index']+=1
        with self.assertRaises(ValueError):r.validate(pre)
    def test_no_reduction_rejected(self):
        pre=copy.deepcopy(self.pre);pre['instruction_reduction']['new']=1049731
        with self.assertRaises(ValueError):r.validate(pre)


if __name__=='__main__':unittest.main()
