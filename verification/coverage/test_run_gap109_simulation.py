import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import run_gap109_simulation as m


class RunnerTests(unittest.TestCase):
    def pre(self):
        return m.life.read_bound(m.PRE/'preflight-manifest.json',m.PRE_SEAL)

    def test_real_preflight(self):
        m.validate(self.pre())
        self.assertEqual(m.BUDGET,600)

    def test_elf_or_baseline_changed(self):
        for key,value in [('binary_sha256','0'*64),('baseline_seal','0'*64),
                          ('binary','/tmp/foreign.elf')]:
            p=self.pre();p[key]=value
            with self.assertRaises(ValueError):m.validate(p)

    def test_contract_counts_and_bool_types(self):
        for key,value in [('dut_checks',40),('host_checks',43),('commands',1),
                          ('vcs_launched',0),('coverage_admitted',True)]:
            p=self.pre();p[key]=value
            with self.assertRaises(ValueError):m.validate(p)

    def test_no_spike_pass_claim(self):
        p=self.pre();p['spike']['custom_isa_pass']=True
        with self.assertRaises(ValueError):m.validate(p)

    def test_site_m8_or_wrong_pc_rejected(self):
        for key,value in [('word',0x0eb5045b),('pc',0x80000000)]:
            p=self.pre();p['elf_proof']['sites'][0][key]=value
            with self.assertRaises(ValueError):m.validate(p)

    def test_vrf_source_csr_extent(self):
        for key,value in [('full_vrf_words_checked',1024),('source_bytes_checked',3440),
                          ('csr_words_checked',12),('m',8)]:
            p=self.pre();p['elf_proof'][key]=value
            with self.assertRaises(ValueError):m.validate(p)

    def test_exact_target_not_guess(self):
        for key,value in [('raw_index',999),('vector','1'),('native_id','999')]:
            p=self.pre();p['targets'][0]['point'][key]=value
            with self.assertRaises(ValueError):m.validate(p)

    def test_no_duplicate_or_extra_target(self):
        for points in ([self.pre()['targets'][0]]*2,self.pre()['targets']*2):
            p=self.pre();p['targets']=points
            with self.assertRaises(ValueError):m.validate(p)

    def test_exact_first_block_must_not_raise_underflow(self):
        p=self.pre();p['numeric_proof']['phase_oracles'][0]['stage_flags'][2]=3
        with self.assertRaises(ValueError):m.validate(p)

    def test_inexact_flags_not_dropped_or_added(self):
        for values in ([8,8],[40,40]):
            p=self.pre();p['expected_csr_fflags']=values
            with self.assertRaises(ValueError):m.validate(p)

    def test_predicted_target_not_claimed_measured(self):
        p=self.pre();p['targets'][0]['measured_hit']=True
        with self.assertRaises(ValueError):m.validate(p)

    def test_no_full_scalar_isa_claim(self):
        p=self.pre();p['spike']['full_scalar_isa_verified']=True
        with self.assertRaises(ValueError):m.validate(p)

    def test_command_raw_traces_no_fsdb(self):
        command=m.command(m.life.OUT/'gap109-test-unused')
        self.assertIn('+NO_FSDB',command)
        self.assertIn('+PRELOAD='+str(m.ELF),command)
        self.assertTrue(any(v.startswith('+VECTOR_TRACE=') for v in command))
        self.assertTrue(any(v.startswith('+COMMIT_TRACE=') for v in command))
        self.assertNotIn('+COMMIT_TOHOST',command)

    def test_no_run_without_external_seal(self):
        with mock.patch.object(m,'prepare') as prepare:
            with self.assertRaises(SystemExit):m.main(['run','--output','/tmp/unused'])
            prepare.assert_not_called()

    def test_existing_output_untouched(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT,prefix='gap109-unit-') as directory:
            p=Path(directory);before=set(p.iterdir())
            with self.assertRaises(ValueError):m.prepare(p)
            self.assertEqual(set(p.iterdir()),before)

    def test_conflicting_expected_pin(self):
        with self.assertRaises(ValueError):m.life.merge_pins({'x':'a'},{'x':'b'})

    def test_open_x_prepared_never_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'prepared';m.life.save(p,{'original':1})
            with self.assertRaises(FileExistsError):m.life.save(p,{'original':2})
            self.assertEqual(json.loads(p.read_text()),{'original':1})

    def test_budget_or_command_rejected_before_launch(self):
        for record in [dict(timeout_s=601,command=[]),dict(timeout_s=600,command=[])]:
            with mock.patch.object(m.subprocess,'Popen') as launch:
                with self.assertRaises(ValueError):m.run(m.life.OUT/'unused',record)
                launch.assert_not_called()



    def test_no_whole_expression_fusion(self):
        p=self.pre();p['numeric_proof']['phase_oracles'][1]['bits']=0x180
        with self.assertRaises(ValueError):m.validate(p)

    def test_probe_ledger_stages_and_flags_not_just_exit0(self):
        for key,value in [('ledger',[0]*52),('stage_operations',11),('returncode',1)]:
            p=self.pre();p['spike'][key]=value
            with self.assertRaises(ValueError):m.validate(p)

    def test_unknown_phase_rejected(self):
        for phase in (True,2,'1'):
            with self.assertRaises(ValueError):m.oracle_expected(phase)


class BackendContract(unittest.TestCase):
    def test_exact_k2_internal_counts_not_external_51(self):
        record=m.life.read_bound(m.PRE/'preflight-manifest.json',m.PRE_SEAL)
        expected=m.backend_contract(record)
        self.assertEqual(expected['integer_results_per_command'],2)
        self.assertEqual(expected['fp_uop_issues_per_command'],12)
        self.assertEqual(expected['accumulator_updates_per_command'],2)
        self.assertEqual(expected['fp_uop_issues_total'],24)
        self.assertEqual(expected['accumulator_updates_total'],4)
        self.assertEqual(expected['architectural_custom_requests'],2)
        self.assertFalse(expected['observed'])

    def test_k1_and_non_affine_shape_rejected(self):
        for key,value in (('k_blocks',1),('weight_profile','Q6_K'),('m',2),('n',2)):
            pre=m.life.read_bound(m.PRE/'preflight-manifest.json',m.PRE_SEAL)
            pre['elf_proof'][key]=value
            with self.assertRaises(ValueError):m.backend_contract(pre)

    def test_second_block_missing_prior_result_or_flags_rejected(self):
        for key,index,value in (('stage_bits',4,0),('stage_flags',10,0),('stage_bits',10,0x25800000)):
            pre=m.life.read_bound(m.PRE/'preflight-manifest.json',m.PRE_SEAL)
            pre['numeric_proof']['phase_oracles'][1][key][index]=value
            with self.assertRaises(ValueError):m.validate(pre)

    def test_source_build_pin_not_replaceable(self):
        with self.assertRaises(ValueError):
            m.life.merge_pins({'/source':'a'*64},{'/source':'b'*64})

if __name__=='__main__':unittest.main()




