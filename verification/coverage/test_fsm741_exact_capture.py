import copy
import json
import unittest
from closure_point_inventory import read_xml
import fsm741_exact_capture as x


class InventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bits = json.loads((x.report.BASE / 'combined-bits.json').read_text())
        cls.shape = read_xml(x.BUILD / 'sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml')

    def test_actual741_exact42_and113(self):
        groups = x.groups_from_shape(self.shape, self.bits)
        self.assertEqual(sum(r['target'] for g in groups for r in g['rows']), 42)
        self.assertEqual(sum(not r['target'] for g in groups for r in g['rows']), 113)
        self.assertTrue(all(not r['target'] for g in groups if g['machine']['name'] == 'lsu_ex_state_q' for r in g['rows']))
        self.assertFalse(x.candidate(x.PORT, 'state_q', 'State', None, 'IDLE'))

    def test_hit_contradiction_rejected(self):
        bits = copy.deepcopy(self.bits)
        bits['metrics']['fsm'][x.PORT]['bits'] = 'fffffff'
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            x.groups_from_shape(self.shape, bits)

    def test_shape_identity_drift_rejected(self):
        bits = copy.deepcopy(self.bits)
        bits['metrics']['fsm'][x.PTW]['checksum'] = '0'
        with self.assertRaisesRegex(ValueError, 'identity'):
            x.groups_from_shape(self.shape, bits)

    def test_only_proven_dispatcher_entries(self):
        for source in ('NORMAL_OPERATION', 'OVERLAP_ISSUE_ORIGINAL', 'WAIT_IDLE', 'WAIT_IDLE_FLUSH'):
            self.assertFalse(x.candidate(x.DISPATCH, 'state_q', 'Transition', source, 'WAIT_STORE_RESPONSE'))
        self.assertFalse(x.candidate(x.DISPATCH, 'state_q', 'State', None, 'WAIT_STORE_RESPONSE'))
        self.assertFalse(x.candidate(x.DISPATCH, 'lsu_ex_state_q', 'Transition', 'OTHER', 'WAIT_STORE_RESPONSE'))


if __name__ == '__main__':
    unittest.main()
