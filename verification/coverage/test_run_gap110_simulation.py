import copy
import unittest
from pathlib import Path
from unittest.mock import patch
import run_gap110_simulation as m


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.pre=m.life.read_bound(m.PRE/'preflight-manifest.json',m.PRE_SEAL)

    def test_real_preflight(self):m.validate(self.pre)

    def test_wrong_elf_or_baseline_or_budget(self):
        for key,value in [('binary_sha256','0'*64),('baseline_seal','0'*64),('budget_s',601)]:
            r=copy.deepcopy(self.pre);r[key]=value
            with self.assertRaises(ValueError):m.validate(r)

    def test_no_fullisa_or_spike_fiction(self):
        for key in ('full_scalar_isa_verified','custom_isa_pass'):
            r=copy.deepcopy(self.pre);r['spike'][key]=True
            with self.assertRaises(ValueError):m.validate(r)

    def test_target_changed_or_hit(self):
        for field,value in [('before_hit',True),('compiled_definition_checksum','0')]:
            r=copy.deepcopy(self.pre);r['targets'][0][field]=value
            with self.assertRaises(ValueError):m.validate(r)

    def test_wrong_native_id_or_generate(self):
        r=copy.deepcopy(self.pre);r['targets'][0]['point']['native_id']='0'
        with self.assertRaises(ValueError):m.validate(r)
        r=copy.deepcopy(self.pre);r['targets'][0]['point']['spec']['generate_info']='slot=0,p=1,r=3,b=2'
        with self.assertRaises(ValueError):m.validate(r)

    def test_target_population(self):
        r=copy.deepcopy(self.pre);r['targets'].pop()
        with self.assertRaises(ValueError):m.validate(r)

    def test_exact_two_phase_oracles(self):
        self.assertEqual([len(m.oracle_expected(i)['bits']) for i in (0,1)],[35,25])
        with self.assertRaises(ValueError):m.oracle_expected(True)

    def test_no_fsdb_and_original_image(self):
        cmd=m.command(m.life.OUT/'gap110-test')
        self.assertEqual(cmd[0],str(m.life.IMAGE));self.assertIn('+NO_FSDB',cmd)
        self.assertIn('+PRELOAD='+str(m.ELF),cmd)
        self.assertEqual(m.BUDGET,600)

    def test_conflicting_pins_rejected(self):
        with self.assertRaises(ValueError):m.life.merge_pins({'/a':'0'*64},{'/a':'1'*64})

    def test_run_requires_external_review(self):
        with patch.object(m,'prepare') as prepare,patch.object(m,'run') as run:
            with self.assertRaises(SystemExit):m.main(['run','--output',str(m.life.OUT/'gap110-test')])
            prepare.assert_not_called();run.assert_not_called()

    def test_prepare_checks_never_launch(self):
        output=m.life.OUT/'gap110-q3-r4-runner-test-unused'
        with patch.object(m.subprocess,'Popen') as launch:
            actual,record=m.prepare(output)
            launch.assert_not_called()
        self.assertEqual(actual,output)
        self.assertFalse(output.exists())
        self.assertEqual(record['expected_backend_vl'],[160,160])
        self.assertFalse(record['coverage_admitted'])

    def test_foreign_output_rejected(self):
        with self.assertRaises(ValueError):m.prepare(Path('/tmp/gap110-test'))


if __name__=='__main__':unittest.main()
