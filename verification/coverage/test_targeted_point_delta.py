import copy
import unittest

from targeted_point_delta import inspect


class TargetedDeltaTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(design={'shape': 'same'}, tests=['old'],
                           metrics={'cond': {'queue': dict(width=3, checksum='a', bits='0x1')}})
        self.after = copy.deepcopy(self.before)
        self.after['tests'].append('new')
        self.after['metrics']['cond']['queue']['bits'] = '0x3'
        self.points = [dict(scope='queue', metric='cond', raw_index=str(i),
                            expression='LZC') for i in range(3)]

    def test_source_index_order(self):
        result = inspect(self.before, self.after, self.points, 'queue', 'LZC')
        self.assertEqual(result['counts'], dict(baseline_unhit=2, newly_hit=1, remaining_unhit=1))
        self.assertEqual(result['newly_hit'][0]['raw_index'], '1')
        self.assertEqual(result['remaining_unhit'][0]['raw_index'], '0')

    def test_incompatible_shape(self):
        self.after['metrics']['cond']['queue']['checksum'] = 'other'
        with self.assertRaises(ValueError):
            inspect(self.before, self.after, self.points, 'queue', '')

    def test_metric_filter_excludes_other_inventory_metrics(self):
        points = [*self.points, dict(scope='queue', metric='line', raw_index='0', expression='LZC')]
        result = inspect(self.before, self.after, points, 'queue', 'LZC')
        self.assertEqual(result['counts']['baseline_unhit'], 2)
        self.assertEqual(result['metric_filter'], 'cond')

    def test_baseline_test_missing(self):
        self.after['tests'] = ['new']
        with self.assertRaises(ValueError):
            inspect(self.before, self.after, self.points, 'queue', '')

    def test_lost_covered_point(self):
        self.after['metrics']['cond']['queue']['bits'] = '0x2'
        with self.assertRaises(ValueError):
            inspect(self.before, self.after, self.points, 'queue', '')


if __name__ == '__main__':
    unittest.main()
