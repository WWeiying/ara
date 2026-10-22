import copy
import json
import unittest
from closure_point_inventory import read_xml
import fsm741_transition_batch as x


class BatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bits = json.loads((x.report.BASE / 'combined-bits.json').read_text())
        cls.shape = read_xml(x.BUILD / 'sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml')

    def test_actual741_exact66_no_manual_state(self):
        groups = x.groups_from_shape(self.shape, self.bits)
        self.assertEqual(sum(r['target'] for g in groups for r in g['rows']), 66)
        self.assertEqual(sum(not r['target'] for g in groups for r in g['rows']), 321)
        self.assertFalse(any(r['target'] for g in groups if g['mode'] == 'State' for r in g['rows']))

    def test_lane_direction_not_reversed(self):
        groups = x.groups_from_shape(self.shape, self.bits)
        for g in groups:
            if g['scope'] in (x.PORT, x.DISPATCH, x.PTW):
                continue
            lane = int(g['scope'].split('gen_lanes[')[1].split(']')[0])
            forbidden = 'LN0_REDUCTION_COMMIT' if lane == 0 else 'SIMD_REDUCTION'
            for r in g['rows']:
                if r['target']:
                    self.assertIn(forbidden, (r['source'], r['destination']))

    def test_hit_contradiction(self):
        b = copy.deepcopy(self.bits)
        scope = next(s for s in x.SOURCES if s.endswith('.i_vmfpu'))
        b['metrics']['fsm'][scope]['bits'] = '1fffffffff'
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            x.groups_from_shape(self.shape, b)

    def test_only_state_display_has_inherited_observation(self):
        hook = x.HOOK.read_text()
        self.assertIn('$expected && [lindex $group 3] eq "State"', hook)
        self.assertIn('(!$observe && $actual != $want)', hook)
        self.assertIn('fs_save first.el\n    fx_audit applied 1', hook)
        self.assertIn('fx_audit final 0', hook)


if __name__ == '__main__':
    unittest.main()
