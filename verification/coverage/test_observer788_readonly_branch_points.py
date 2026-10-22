"""Read-only compiled-checksum/foreign-point replay; no capture or disk writes."""
import unittest

import report_population788_observers as owner
from test_observer788_readonly_counterexamples import fixtures, SCOPES


class BranchPointCounterexample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ob, cls.old, guard, _, _ = fixtures()
        lines = [guard]
        for item in cls.ob['compiled_scopes']:
            lines.extend([
                'CHECKSUM: "%s %s"' % (item['design_module_checksum'], item['toggle_checksum']),
                'INSTANCE: '+item['scope'],
            ])
            for node, name, _, _, _, left, right in item['typed_inventory']:
                decl = name if node == 'node' else name+'['+left+':'+right+']'
                lines.append('Toggle '+name+' "logic '+decl+'"')
        cls.full = '\n'.join(lines)+'\n'

    def test_control_full_typed_toggle_preserves_old_padding(self):
        owner.native_gate(self.full, self.old, self.ob)

    def test_real_branch_checksum_foreign_point_must_reject(self):
        checksum = self.ob['per_metric_checksums'][SCOPES[0]]['branch']
        self.assertEqual(checksum, ['2887169998'])
        # Frozen bind Branch capacity is four, not point 999999.
        self.assertEqual(self.ob['capacities'][SCOPES[0]]['branch'], 4)
        foreign = ('CHECKSUM: "2332976182 2887169998"\nINSTANCE: '+
                   SCOPES[0]+'\nBranch 999999\n')
        with self.assertRaises(ValueError, msg='BLOCKER: real checksum accepted foreign Branch point'):
            owner.native_gate(self.full+foreign, self.old, self.ob)


if __name__ == '__main__':
    unittest.main()
