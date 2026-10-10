import copy
import unittest

from inventory_fp16_pack_lower_bound_705 import build_inventory, classify


class FP16PackInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = build_inventory()

    def test_exact208_and936(self):
        self.assertEqual(len(self.inventory['candidates']), 208)
        self.assertEqual(len(self.inventory['protected']), 936)
        self.assertEqual({r['point']['raw_index'] for r in self.inventory['candidates']}, set(range(30, 56)))
        self.assertFalse(any(r['raw_hit'] for r in self.inventory['candidates']))

    def test_boundary_and_reachable_gaps_preserved(self):
        rows = [r for r in self.inventory['protected'] if r['decision'] == 'PROTECTED_MINUS25_BOUNDARY']
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(r['raw_hit'] for r in rows), 1)
        self.assertEqual({r['point']['raw_index'] for r in rows}, {56})
        self.assertEqual(sum(s['reachable_or_unclassified_zero'] for s in self.inventory['scope_statistics']), 118)

    def test_observed_candidate_hit_rejected(self):
        row = self.inventory['candidates'][0]
        with self.assertRaises(ValueError):
            classify(row['point'], {row['point']['vector']: row['case']}, True)

    def test_wrong_raw_binding_rejected(self):
        row = self.inventory['candidates'][0]
        point = copy.deepcopy(row['point'])
        point['raw_index'] = 56
        with self.assertRaises(ValueError):
            classify(point, {point['vector']: row['case']}, False)

    def test_defaults_preserved(self):
        rows = [r for r in self.inventory['protected'] if r['decision'] == 'PROTECTED_DEFAULT']
        self.assertEqual(len(rows), 16)
        self.assertEqual({r['point']['raw_index'] for r in rows}, {28, 29})


if __name__ == '__main__':
    unittest.main()
