"""Runner gates and subprocess failure semantics; no EDA launched."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import run_gap105_simulation as m


class Gates(unittest.TestCase):
    def setUp(self):
        self.pre = m.life.read_bound(m.PRE/'preflight-manifest.json',m.PRE_SEAL)

    def test_real_sealed_preflight_contract(self):
        m.validate(self.pre)

    def test_no_functional_spike_claim(self):
        for key, value in [('custom_isa_pass',True),('qbs_app_spike_executed',True),
                           ('capability_probe_completed',False)]:
            pre = copy.deepcopy(self.pre)
            pre['spike'][key] = value
            with self.assertRaises(ValueError): m.validate(pre)

    def test_checks_phases_and_full_vrf(self):
        for key,value in [('dut_checks',40),('commands',1),('phase_order',[8,4]),
                          ('full_vrf_words_per_command',512),('host_negative_tests',33),
                          ('coverage_admitted',True),('binary_sha256','0'*64)]:
            pre = copy.deepcopy(self.pre); pre[key] = value
            with self.assertRaises(ValueError): m.validate(pre)

    def test_exact_elf_pc_opcode_and_csr(self):
        for key,value in [('vl',256),('vstart',1),('source_bytes_checked',0),
                          ('csr_words_checked',0),('activation_mod16',[0,8])]:
            pre = copy.deepcopy(self.pre); pre['elf_proof'][key] = value
            with self.assertRaises(ValueError): m.validate(pre)
        pre = copy.deepcopy(self.pre); pre['elf_proof']['sites'][1]['pc'] += 4
        with self.assertRaises(ValueError): m.validate(pre)
        pre = copy.deepcopy(self.pre); pre['elf_proof']['sites'][0]['word'] ^= 1
        with self.assertRaises(ValueError): m.validate(pre)

    def test_duplicate_target_rejected(self):
        self.pre['targets'][1] = self.pre['targets'][0]
        with self.assertRaises(ValueError): m.validate(self.pre)

    def test_no_fsdb_no_fake_htif_and_all_raw_outputs(self):
        output = m.life.OUT/'test-gap105-never-launched'
        cmd = m.command(output)
        self.assertIn('+NO_FSDB',cmd)
        self.assertIn('+QBS_PERF',cmd)
        self.assertIn('+COMMIT_TRACE='+str(output/'commit_trace.csv'),cmd)
        self.assertIn('+VECTOR_TRACE='+str(output/'vector_trace.csv'),cmd)
        self.assertIn(str(output/'code.vdb'),cmd)
        self.assertFalse(any(x.startswith('+COMMIT_TOHOST') for x in cmd))

    def test_expected_pins_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            m.life.merge_pins({str(m.ELF):m.ELF_SEAL},{str(m.ELF):'0'*64})

    def test_alias_and_existing_output_rejected_before_audit(self):
        for output in (m.life.OUT/'../out/unused-gap105',m.PRE,Path('/tmp/gap105')):
            with patch.object(m.life,'read_bound') as read:
                with self.assertRaises(ValueError): m.prepare(output)
                read.assert_not_called()

    def test_frozen_helper_drift_rejected(self):
        with patch.object(m.life,'digest',return_value='0'*64), patch.object(m.life,'read_bound') as read:
            with self.assertRaises(ValueError): m.prepare(m.life.OUT/'never-gap105')
            read.assert_not_called()

    def test_missing_external_run_seal_no_launch(self):
        with patch.object(m,'run') as launch, patch.object(m,'prepare') as prep:
            with self.assertRaises(SystemExit): m.main(['run','--output',str(m.life.OUT/'unused')])
            launch.assert_not_called(); prep.assert_not_called()

    def test_wrong_reviewed_contract_no_launch(self):
        output = m.life.OUT/'unused-gap105'
        with patch.object(m,'prepare',return_value=(output,{'pins':{}})), \
             patch.object(m.life,'read_bound',return_value={'pins':{},'changed':True}), \
             patch.object(m,'run') as launch:
            with self.assertRaises(ValueError):
                m.main(['run','--output',str(output),'--prepared-seal','0'*64])
            launch.assert_not_called()


class Execution(unittest.TestCase):
    def simulate(self, mode):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        output = Path(temp.name)/'run'
        manifest = dict(pins={str(m.ELF):m.ELF_SEAL},timeout_s=m.BUDGET,command=m.command(output))
        child = Mock(pid=23456)
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired('simv',m.BUDGET),-9] if mode=='timeout' else None
        if mode!='timeout': child.wait.return_value = 0 if mode=='success' else 1
        with patch.object(m.life,'check'), patch.object(m.subprocess,'Popen',return_value=child) as launch, \
             patch.object(m.os,'killpg') as kill:
            if mode=='success': m.run(output,manifest)
            else:
                with self.assertRaises((ValueError,subprocess.TimeoutExpired)): m.run(output,manifest)
            launch.assert_called_once()
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertEqual(child.wait.call_args_list[0].kwargs,dict(timeout=1200))
            if mode=='timeout': kill.assert_called_once_with(child.pid,m.signal.SIGKILL)
            status = json.loads((output/'simulation-status.json').read_text())
            self.assertFalse(status['coverage_admitted'])
            self.assertFalse(status['admission_performed'])
            self.assertEqual(json.loads((output/'started.json').read_text())['pid'],child.pid)
            self.assertTrue((output/'console.log').exists())
            return status

    def test_exit_zero_is_not_qualification(self):
        status = self.simulate('success')
        self.assertEqual(status['status'],'SIMULATION_EXITED_NOT_ADMITTED')
        self.assertFalse(status['dut_self_check_verified'])
        self.assertFalse(status['spike_custom_isa_pass'])

    def test_nonzero_preserved_no_retry(self):
        self.assertEqual(self.simulate('nonzero')['status'],'SIMULATION_NOT_ADMITTED')

    def test_timeout_kills_process_group_no_retry(self):
        self.assertEqual(self.simulate('timeout')['status'],'SIMULATION_NOT_ADMITTED')

    def test_budget_or_command_cannot_be_extended(self):
        output = Path('/tmp/unused-gap105')
        for manifest in (dict(timeout_s=1201,command=m.command(output)),
                         dict(timeout_s=1200,command=m.command(output)+['+FSDB'])):
            with patch.object(m.subprocess,'Popen') as launch:
                with self.assertRaises(ValueError): m.run(output,manifest)
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
