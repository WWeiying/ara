import copy
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('reviewed_export',
        ROOT / 'verification/coverage/run_reviewed_dve_20261004.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class NativeExclusions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = module.audit.jread(module.REVIEW / 'policy.json')
        cls.record = module.audit.jread(module.REVIEW / 'audit.json')
        cls.points = module.native_points(cls.policy)

    def test_policy_bound_to_review(self):
        module.audit.validate_policy(self.policy, self.record)

    def test_exact_points(self):
        self.assertEqual(len(module.validate_native(self.points, self.policy, False)), 94)

    def test_missing(self):
        text = '\n'.join(self.points.splitlines()[:-4])
        with self.assertRaises(ValueError):
            module.validate_native(text, self.policy, False)

    def test_extra(self):
        with self.assertRaises(ValueError):
            module.validate_native(self.points + self.points[:self.points.index('CHECKSUM:', 1)],
                                   self.policy, False)

    def test_point_signature(self):
        with self.assertRaises(ValueError):
            module.validate_native(self.points.replace('if (flush_i)', 'if (1)', 1), self.policy, False)

    def test_point_checksum(self):
        with self.assertRaises(ValueError):
            module.validate_native(self.points.replace('3393845244', '1', 1), self.policy, False)

    def test_branch_false_not_allowed(self):
        with self.assertRaises(ValueError):
            module.validate_native(self.points.replace('(0) "flush_i 1"', '(1) "flush_i 0"', 1),
                                   self.policy, False)

    def test_wildcard(self):
        with self.assertRaises(ValueError):
            module.validate_native(self.points.replace('gen_lanes[0]', 'gen_lanes[*]', 1), self.policy, False)

    def test_exact_observers(self):
        text = self.points
        for p in self.policy['allowed_observers']:
            text += 'CHECKSUM: "' + ' '.join(p['checksum']) + '"\nINSTANCE: ' + p['scope'] + '\n'
        self.assertEqual(len(module.validate_native(text, self.policy, True)), 104)
        with self.assertRaises(ValueError):
            module.validate_native(text.replace('i_llm_perf_monitor', 'i_ara'), self.policy, True)

    def test_policy_cannot_broaden(self):
        other = copy.deepcopy(self.policy)
        other['allowed_observers'][0]['scope'] = 'ara_tb'
        with self.assertRaises(ValueError):
            module.audit.validate_policy(other, self.record)

    def test_snapshot_adapter_rejects_broadened_identity(self):
        spec = importlib.util.spec_from_file_location('native_adapter',
                module.REVIEW / 'prepare_native.py')
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        base = SimpleNamespace()
        adapter.configure(dict(policy=self.policy, observers=self.record['observers'],
                               shape_files={}), base, module.audit)
        self.assertEqual(base.exclusion_items(self.points), base.approved_points())
        with self.assertRaises(ValueError):
            base.exclusion_items(self.points.replace('3998926456', '0', 1))
        with self.assertRaises(ValueError):
            base.scopes(b'not the reviewed design')

    def test_observer_missing_and_extra(self):
        with self.assertRaises(ValueError):
            module.validate_native(self.points, self.policy, True)
        text = self.points + 'CHECKSUM: "1"\nINSTANCE: ara_tb\n'
        with self.assertRaises(ValueError):
            module.validate_native(text, self.policy, True)


if __name__ == '__main__':
    unittest.main()
