from pathlib import Path
import unittest
from unittest.mock import patch

import report_native_population_union_v2 as adapter
import test_report_native_population_union as previous


class RootTests(unittest.TestCase):
    def test_actual_all_eight_cast_names_not_inferred_leaf(self):
        c, _ = previous.fixture()
        for instance in c['cast_config']['instances']:
            scope = instance['scope']
            actual = adapter.root_name(scope)
            self.assertIn('gen_num_lanes[', actual)
            self.assertTrue(scope.endswith('.' + actual))
            self.assertNotEqual(actual, scope.split('.')[-1])

    def test_missing_scope_rejected(self):
        with self.assertRaises(ValueError):
            adapter.root_name('unknown.scope')

    def test_private_entry_and_verifier_keep_new_binding(self):
        ns = adapter.namespace()
        self.assertEqual(ns['__file__'], adapter.__file__)
        self.assertIs(ns['check'].__globals__, ns)
        self.assertIs(ns['verify'].__globals__, ns)
        self.assertIs(ns['run'].__globals__, ns)
        self.assertIs(ns['records'], adapter.predecessor.records)
        self.assertIs(ns['TCL'], adapter.predecessor.TCL)

    def test_predecessor_drift_rejected(self):
        with patch.object(adapter.life, 'check', side_effect=ValueError('drift')):
            with self.assertRaisesRegex(ValueError, 'drift'):
                adapter.namespace()


if __name__ == '__main__':
    unittest.main()
