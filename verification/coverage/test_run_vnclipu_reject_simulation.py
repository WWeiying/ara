import copy
import json
import os
from pathlib import Path
import unittest

import run_vnclipu_reject_simulation as r


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = Path(os.environ.get('VNCLIPU_PREFLIGHT', str(r.PRE)))
        cls.pre = json.loads((out / 'preflight-manifest.json').read_text())

    def reject(self, key, value):
        pre = copy.deepcopy(self.pre); pre[key] = value
        with self.assertRaises(ValueError): r.validate(pre)

    def test_actual_contract(self): r.validate(self.pre)
    def test_budget(self): self.assertEqual(r.BUDGET, 1200)
    def test_command(self):
        c = r.command(r.life.OUT / 'unused-vnclipu-test-output')
        self.assertEqual(c[0], str(r.life.IMAGE)); self.assertIn('+NO_FSDB', c)
        self.assertIn('+PRELOAD=' + str(r.PRE / 'input.elf'), c)
        self.assertTrue(any(x.startswith('+COMMIT_TRACE=') for x in c))
        self.assertTrue(any(x.startswith('+VECTOR_TRACE=') for x in c))
        self.assertNotIn('dve', ' '.join(c).lower())
    def test_wrong_baseline(self): self.reject('baseline_tests', 723)
    def test_false_admitted(self): self.reject('coverage_admitted', True)
    def test_simulated_claim(self): self.reject('vcs_started', True)
    def test_zcc(self): self.reject('ZCC_executed', True)
    def test_oracle_missing(self): self.reject('validation', {})
    def test_wrong_elf(self): self.reject('input_elf', '/tmp/other.elf')
    def test_native_raw_drift(self):
        pre = copy.deepcopy(self.pre); pre['targets'][0]['raw_index'] += 1
        with self.assertRaises(ValueError): r.validate(pre)
    def test_wrong_scope_port(self):
        pre = copy.deepcopy(self.pre); pre['targets'][0]['scope'] += '.req_ports[2]'
        with self.assertRaises(ValueError): r.validate(pre)
    def test_target_already_hit(self):
        pre = copy.deepcopy(self.pre); pre['targets'][0]['hit725'] = True
        with self.assertRaises(ValueError): r.validate(pre)
    def test_missing_pinned_trace(self):
        pre = copy.deepcopy(self.pre); del pre['pins'][str(r.PRE / 'spike.trace')]
        with self.assertRaises(ValueError): r.validate(pre)


if __name__ == '__main__': unittest.main()
