"""Pure WAR raw diagnostic contracts; synthetic negatives, no DUT execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import prepare_pure_war_raw_gain as h


class RawPlanTests(unittest.TestCase):
    def setUp(self):
        self.original = dict(tests=[f'vdb{i}' for i in range(729)], design={'shape': 'fixed'},
                             input_hashes={'/old': 'a' * 64}, metrics={})
        self.before = copy.deepcopy(self.original)
        self.before['tests'].append('vdb729')
        self.base = h.life.OUT / 'formal730'
        self.manifest = dict(output=str(self.base), output_pins={str(self.base / 'status.json'): 'b' * 64})
        self.status = dict(aggregate_passed=730, coverage_admitted=True, status='PASS_RAW_UNION_HISTORICAL_ONLY')

    def gate(self):
        return h.baseline_contract(self.manifest, self.status, self.before, self.original, self.base)

    def test_successor_prefix(self):
        self.assertEqual(self.gate(), 730)

    def test_reordered_prefix(self):
        self.before['tests'][0:2] = self.before['tests'][1::-1]
        with self.assertRaises(ValueError): self.gate()

    def test_duplicate_baseline(self):
        self.before['tests'][-1] = self.before['tests'][0]
        with self.assertRaises(ValueError): self.gate()

    def test_unadmitted_baseline(self):
        self.status['coverage_admitted'] = False
        with self.assertRaises(ValueError): self.gate()

    def test_wrong_count(self):
        self.status['aggregate_passed'] = 729
        with self.assertRaises(ValueError): self.gate()

    def test_design_drift(self):
        self.before['design'] = {'shape': 'drift'}
        with self.assertRaises(ValueError): self.gate()

    def test_alias_outputs(self):
        self.manifest['output_pins'] = {'/outside/status.json': 'b' * 64}
        with self.assertRaises(ValueError): self.gate()

    def test_conflicting_input_pin(self):
        self.before['input_hashes']['/old'] = 'b' * 64
        with self.assertRaises(ValueError): self.gate()

    def test_qualification(self):
        record = json.loads(h.QUAL.read_bytes())
        h.qualification_contract(record)
        for key, value in [('status', 'FAIL'), ('coverage_admitted', True),
                           ('run', '/wrong'), ('rtl_changed', True)]:
            mutated = dict(record, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.qualification_contract(mutated)

    def test_exact_four_compiled_targets(self):
        pre = json.loads((h.q.runner.PRE / 'preflight-manifest.json').read_bytes())
        before = json.loads((h.BASE729 / 'combined-bits.json').read_bytes())
        h.target_contract(pre['targets'], before)
        for key, value in [('raw_index', 665), ('scope', 'wrong'), ('metric', 'branch')]:
            targets = copy.deepcopy(pre['targets']); targets[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.target_contract(targets, before)
        with self.assertRaises(ValueError): h.target_contract(pre['targets'][:3], before)

    def test_singleton_union_and_zero_gain_preserved(self):
        run = Path('/run')
        before = dict(design={'d': 'x'}, tests=['old'], input_hashes={'/a': 'a' * 64},
                      metrics={'cond': {'ara_tb.dut.i_ara_soc.i_system': dict(width=2, checksum='1', bits='0x1')}})
        single = copy.deepcopy(before); single['tests'] = ['/run/code.vdb']
        after, delta = h.combine(before, single, run)
        self.assertEqual(after['tests'], ['old', '/run/code.vdb'])
        self.assertEqual(delta['metrics'], {'cond': 0})
        single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system']['bits'] = '0x2'
        self.assertEqual(h.combine(before, single, run)[1]['metrics'], {'cond': 1})
        single['tests'] = ['old']
        with self.assertRaises(ValueError): h.combine(before, single, run)

    def test_pin_drift_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input'
            with path.open('x') as stream: stream.write('original')
            pins = {str(path): h.life.digest(path)}
            with path.open('w') as stream: stream.write('drift')
            with self.assertRaises(ValueError): h.life.check(pins)


if __name__ == '__main__':
    unittest.main()
