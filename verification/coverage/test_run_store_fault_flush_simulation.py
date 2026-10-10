import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import run_store_fault_flush_simulation as p


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((p.PRE / 'preflight-manifest.json').read_bytes())
        self.out = p.life.OUT / 'store-fault-flush-test-no-launch'

    def verify_mock(self):
        with patch.object(p.life, 'read_bound', return_value=copy.deepcopy(self.pre)), \
             patch.object(p.life, 'check'):
            return p.verify_preflight(p.PRE, p.PRE_SEAL)

    def test_actual_parent_reference_strict134_replay(self):
        result = self.verify_mock()
        self.assertEqual(result['validation']['checks'],134)
        self.assertEqual(result['validation']['cause'],7)
        self.assertEqual(result['validation']['fault_vstart'],0)

    def test_foreign_preflight_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,'Exact parent'): p.verify_preflight(p.PRE,'foreign')

    def test_reduced_checks_rejected(self):
        self.pre['validation']['checks']=133
        with self.assertRaisesRegex(ValueError,'Strict134'): self.verify_mock()

    def test_wrong_trap_contract_rejected(self):
        for key,value in [('cause',6),('fault_vstart',1),('tval',p.p.BAD+6)]:
            old=self.pre['validation'][key]; self.pre['validation'][key]=value
            with self.assertRaisesRegex(ValueError,'Strict134'): self.verify_mock()
            self.pre['validation'][key]=old

    def test_false_admission_or_DUT_claim_rejected(self):
        for key in ('vcs_started','coverage_admitted','native_timing_observed'):
            self.pre[key]=True
            with self.assertRaisesRegex(ValueError,'preflight contract'): self.verify_mock()
            self.pre[key]=False

    def test_no_FSDB_and_exact_trace_coverage_command(self):
        command=p.command(self.out,p.PRE)
        self.assertEqual(command.count('+NO_FSDB'),1)
        self.assertIn('+PRELOAD='+str(p.PRE/'input.elf'),command)
        self.assertIn('+COMMIT_TRACE='+str(self.out/'commit_trace.csv'),command)
        self.assertIn('+VECTOR_TRACE='+str(self.out/'vector_trace.csv'),command)
        self.assertIn('line+cond+fsm+tgl+branch',command)
        self.assertFalse(any(x.startswith('-m0x') for x in command))

    def test_existing_run_rejected_before_preflight(self):
        with patch.object(p,'verify_preflight') as verify:
            with self.assertRaisesRegex(ValueError,'Fresh direct'): p.prepare(p.PRE,p.PRE,p.PRE_SEAL)
            verify.assert_not_called()

    def test_missing_image_pin_and_foreign_image_rejected(self):
        for image in ({}, {str(p.life.IMAGE):'foreign'}):
            with patch.object(p,'verify_preflight',return_value=self.pre), \
                 patch.object(p.life,'read_bound',return_value={'simv':str(p.life.IMAGE),'image':image}):
                with self.assertRaisesRegex(ValueError,'simv66'): p.prepare(self.out,p.PRE,p.PRE_SEAL)

    def test_lifecycle_bindings_restored_after_failure_no_EDA(self):
        manifest={'preflight':str(p.PRE/'preflight-manifest.json'),'preflight_seal':p.PRE_SEAL,
                  'elf_sha256':self.pre['input_elf_sha256']}
        old={k:getattr(p.frozen,k) for k in ('PRE','ELF_SEAL','preflight','command')}
        with patch.object(p,'prepare',return_value=manifest), \
             patch.object(p.frozen,'run',side_effect=ValueError('mock failure')) as run:
            with self.assertRaisesRegex(ValueError,'mock failure'): p.invoke_run(self.out,manifest)
            run.assert_called_once_with(self.out,manifest)
        for k,v in old.items(): self.assertIs(getattr(p.frozen,k),v)

    def test_execution_drift_never_calls_lifecycle(self):
        manifest={'preflight':str(p.PRE/'preflight-manifest.json'),'preflight_seal':p.PRE_SEAL}
        with patch.object(p,'prepare',return_value={'different':True}),patch.object(p.frozen,'run') as run:
            with self.assertRaisesRegex(ValueError,'execution drift'): p.invoke_run(self.out,manifest)
            run.assert_not_called()


if __name__=='__main__': unittest.main()
