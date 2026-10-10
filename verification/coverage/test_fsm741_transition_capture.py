import copy
import json
import unittest
from closure_point_inventory import read_xml
import fsm741_transition_capture as x


class TransitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bits = json.loads((x.report.BASE / 'combined-bits.json').read_text())
        cls.shape = read_xml(x.BUILD / 'sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml')

    def test_exact34_all38_states_protected(self):
        groups = x.groups_from_shape(self.shape, self.bits)
        self.assertEqual(sum(r['target'] for g in groups for r in g['rows']), 34)
        self.assertEqual(sum(not r['target'] for g in groups for r in g['rows']), 121)
        states = [r for g in groups if g['mode'] == 'State' for r in g['rows']]
        self.assertEqual(len(states), 38)
        self.assertFalse(any(r['target'] for r in states))

    def test_hit_transition_rejected(self):
        bits = copy.deepcopy(self.bits)
        bits['metrics']['fsm'][x.PORT]['bits'] = 'fffffff'
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            x.groups_from_shape(self.shape, bits)

    def test_target_groups_exact(self):
        groups = x.groups_from_shape(self.shape, self.bits)
        self.assertEqual([sum(r['target'] for g in groups if g['scope'] == s for r in g['rows']) for s in x.SOURCES], [20, 11, 3])


if __name__ == '__main__':
    unittest.main()
