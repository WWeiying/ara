from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import run_gap104_simulation as m


class RunnerTests(unittest.TestCase):
    def pre(self):return json.loads((m.PRE/'preflight-manifest.json').read_bytes())

    def test_actual_preflight(self):
        self.assertEqual(m.life.digest(m.PRE/'preflight-manifest.json'),m.PRE_SEAL)
        m.validate(self.pre())

    def test_wrong_case_base_or_checks(self):
        for key,value in (('baseline_tests',719),('case','vgap101_illegal_segment_store'),
                          ('checks',1075),('vcs_started',True),('coverage_admitted',True)):
            pre=self.pre();pre[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate(pre)

    def test_full_oracle_not_only_traps(self):
        for key,value in (('illegal_traps',1),('unchanged_vrf_bytes',4096),
                          ('unchanged_target_guard_bytes',64),('recovery_guard_bytes',64)):
            pre=self.pre();pre['validation'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate(pre)

    def test_exact_opcode_and_pc(self):
        pre=self.pre();pre['opcodes'][1]=0x22050fa7
        with self.assertRaises(ValueError):m.validate(pre)
        pre=self.pre();pre['symbols']['g104_bad_b']+=4
        with self.assertRaises(ValueError):m.validate(pre)

    def test_expected_elf_pin_not_overwritten(self):
        pre=self.pre();pre['pins'][str(m.ELF)]='a'*64
        with self.assertRaises(ValueError):m.validate(pre)

    def test_missing_preflight_pin(self):
        for name in ('spike.trace','host-reference','target-before.json'):
            pre=self.pre();pre['pins'].pop(str(m.PRE/name))
            with self.subTest(name=name),self.assertRaises(ValueError):m.validate(pre)

    def test_command_frozen_elf_trace_coverage_no_fsdb(self):
        out=m.life.OUT/'gap104-fixture-not-created';cmd=m.command(out)
        self.assertEqual(cmd[0],str(m.life.IMAGE))
        self.assertEqual(cmd.count('+NO_FSDB'),1)
        self.assertIn('+PRELOAD='+str(m.ELF),cmd)
        self.assertIn('+COMMIT_TRACE='+str(out/'commit_trace.csv'),cmd)
        self.assertIn('+VECTOR_TRACE='+str(out/'vector_trace.csv'),cmd)
        self.assertIn(str(out/'code.vdb'),cmd)
        self.assertNotIn('+FSDB',cmd)

    def test_no_unsealed_run(self):
        with patch.object(m.life,'run') as run:
            with self.assertRaises(SystemExit):m.main(['run','--output',str(m.life.OUT/'not-created')])
            run.assert_not_called()

    def test_wrong_prepared_contract_cannot_launch(self):
        out=m.life.OUT/'gap104-fixture-not-created'
        with patch.object(m,'prepare',return_value=(out,{'sealed':1})),\
             patch.object(m.life,'read_bound',return_value={'sealed':2}),patch.object(m.life,'run') as run:
            with self.assertRaisesRegex(ValueError,'Reviewed prepared'):
                m.main(['run','--output',str(out),'--prepared-seal','a'*64])
            run.assert_not_called()

    def test_pin_conflict(self):
        with self.assertRaises(ValueError):m.life.merge_pins({'file':'a'*64},{'file':'b'*64})

    def test_runtime_path_rejected_before_audit(self):
        for out in (m.life.OUT,m.PRE,m.life.OUT/'..'/'outside-output'):
            with self.assertRaisesRegex(ValueError,'Fresh independent'):m.prepare(out)

    def test_frozen_lifecycle_hash_rejected(self):
        with patch.object(m.life,'digest',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'Frozen lifecycle'):
                m.prepare(m.life.OUT/'gap104-fixture-not-created')


if __name__=='__main__':unittest.main()
