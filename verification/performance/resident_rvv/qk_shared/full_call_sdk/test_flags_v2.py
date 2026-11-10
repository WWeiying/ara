"""Run in the successor bundle with its explicitly corrected fixture.py."""
import copy
import importlib
from pathlib import Path
import tempfile
import unittest

import fixture as f
import check as c


class FlagsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='sdk_pv_flags_v2_')
        cls.fixture,_ = f.generate(Path(cls.temp.name))
        case = dict(dimension=64,heads=1,kv_heads=1,tokens=2,capacity=2,initial_flags=8)
        # Inexact probability->F16, but all V=0 and seed=0: hardware FMAs exact.
        query = [f.raw32(1.0001)]+[0]*127
        key = [0]*128+[0x3c00]+[0]*127
        data = dict(query=f.pack(query,32),key=f.pack(key,16),
                    value=f.pack([0]*256,16),mask=f.pack([0,0],16))
        cls.prep_only = f.reference(case,data)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_prep_only_nx_not_hardware_or_incoming_sticky(self):
        stages = {r['mode']:r['fflags'] for r in self.prep_only['stages']}
        self.assertEqual(stages['PV_PREP'],1)
        self.assertEqual(stages['PV'],0)
        self.assertEqual(self.prep_only['bits'],[0]*64)
        self.assertEqual(self.prep_only['natural_flags'],1)
        self.assertEqual(self.prep_only['expected_fcsr'],9)
        tiny = dict(results=[self.prep_only]*3)
        command = dict(trial=1,group=0,base=0,heads=1,tile=0,mode='PV')
        self.assertEqual(c.local_flags(tiny,command),0)

    def test_hardware_probe_cannot_credit_prep_or_sticky(self):
        tests = importlib.import_module('test_sdk')
        fixture = copy.deepcopy(self.fixture)
        for stage in fixture['results'][1]['stages']:
            if stage['tile']==0 and stage['mode'] in ('PV','PV_PREP'):
                stage['fflags'] = 0 if stage['mode']=='PV' else 1
        text = tests.perf_fixture(fixture)
        self.assertEqual(len(c.resident_performance(text,fixture)),22)
        lane = next(r for r in text.splitlines() if r.startswith('[RESIDENT_PV_LANE]'))
        terminal = next(r for r in text.splitlines() if r.startswith('[RESIDENT_PV_PERF]'))
        self.assertIn('flags=0',lane)
        self.assertIn('flags=0',terminal)
        for borrowed in (1,8):
            changed = text.replace(lane,lane.replace('flags=0','flags='+str(borrowed)),1)
            changed = changed.replace(terminal,terminal.replace('flags=0','flags='+str(borrowed)),1)
            with self.subTest(borrowed=borrowed),self.assertRaisesRegex(ValueError,'command flags'):
                c.resident_performance(changed,fixture)

    def test_derived_expf_exact_zero_samples_and_global_unchanged(self):
        expected = dict(input=0,output=0x3f800000,fflags=0)
        self.assertEqual(self.fixture['results'][2]['expf_samples'],[expected]*6)
        self.assertEqual(self.fixture['scalar_expf_portability']['derived'],
            'All six inputs +0: expf(+0)=1 exactly, flags=0; no host/target approximation assumption')
        self.assertEqual([r['natural_flags'] for r in self.fixture['results']],[3,3,3])
        self.assertEqual([r['expected_fcsr'] for r in self.fixture['results']],[3,11,3])
        self.assertEqual(f.sha(Path(self.temp.name)/'golden_0.bin'),f.NATIVE_SHA)
        self.assertEqual(f.sha(Path(self.temp.name)/'golden_2.bin'),
                         '19f95bebaac1071ae2b93a5e9cdfdd3c7a9dacbca7223f6d87dbe82d2864470e')


if __name__ == '__main__':
    unittest.main()
