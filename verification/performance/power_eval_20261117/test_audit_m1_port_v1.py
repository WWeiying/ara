import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('audit_m1_port_v1.py'))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class Tests(unittest.TestCase):
    def fixture(self):
        fields = ('signals', 'first_tick', 'last_tick', 'duration_ticks', 'clock_edges', 'retire_samples',
                  'pc_unknown_when_committing', 'initial_value_records', 'initial_unknown_value_records',
                  'top_committing_pcs', 'active_payload_unknown_samples', 'pv_fpu_samples')
        old = {k: 0 for k in fields}
        old['first_tick'] = 10000
        report = dict(old, anchor_episode_ticks=[20000, 30000, 40000, 50000], mac_episode_ticks=[1, 2, 3, 4])
        plan = dict(first_cycle=1, last_cycle=10)
        pairs = [dict(cycle=x) for x in (2, 3, 4, 5)]
        return report, old, plan, pairs

    def test_same_phase(self):
        result = a.validate(*self.fixture())
        self.assertEqual(result['gate_minus_rtl_cycles'], [0, 0, 0, 0])

    def test_control_disagreement_rejected(self):
        report, old, plan, pairs = self.fixture()
        report['pc_unknown_when_committing'] = 1
        with self.assertRaises(ValueError):
            a.validate(report, old, plan, pairs)

    def test_real_displacement_rejected(self):
        report, old, plan, pairs = self.fixture()
        report['anchor_episode_ticks'] = [x + 30000 for x in report['anchor_episode_ticks']]
        with self.assertRaises(ValueError):
            a.validate(report, old, plan, pairs)

    def test_missing_mac_rejected(self):
        report, old, plan, pairs = self.fixture()
        report['mac_episode_ticks'] = []
        with self.assertRaises(ValueError):
            a.validate(report, old, plan, pairs)


if __name__ == '__main__':
    unittest.main()
