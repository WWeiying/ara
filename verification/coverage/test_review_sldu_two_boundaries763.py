import copy
import unittest

import review_sldu_two_boundaries763 as p


class Boundaries(unittest.TestCase):
    def test_np2_overrides_not_run(self):
        for input_done, output_done, finished in ((False, False, False),
                                                (True, False, False),
                                                (True, True, False),
                                                (True, True, True)):
            self.assertNotEqual(p.common_next('SLIDE_NP2_COMMIT', 'VSLIDEUP', False,
                                              True, input_done, output_done, finished, False),
                                'SLIDE_RUN')

    def test_up_identity_and_bad_opcode_negative(self):
        self.assertEqual(p.common_next('SLIDE_RUN_VSLIDE1UP_FIRST_WORD', 'VSLIDEUP', True,
                                      True, False, False, True, False), 'SLIDE_IDLE')
        self.assertEqual(p.common_next('SLIDE_RUN_VSLIDE1UP_FIRST_WORD', 'VSLIDEDOWN', True,
                                      True, False, False, True, False),
                         'SLIDE_EMIT_VSLIDE1DOWN_SCALAR')

    def test_scalar_emit_for_np2_is_not_waived(self):
        self.assertEqual(p.common_next('SLIDE_NP2_COMMIT', 'VSLIDEDOWN', True,
                                      True, False, False, True, False),
                         'SLIDE_EMIT_VSLIDE1DOWN_SCALAR')

    def test_flush_precedence(self):
        self.assertEqual(p.common_next('SLIDE_NP2_COMMIT', 'VSLIDEDOWN', True,
                                      True, True, True, True, True), 'SLIDE_IDLE')

    def test_real_shape_and_observed_target_rejection(self):
        a = p.life.read_bound(p.BASE/'admission-manifest.json', p.BASE_SHA)
        path = p.BASE/'combined-bits.json'
        b = p.life.read_bound(path, a['output_pins'][str(path)])
        shape = p.life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'
        tree = p.native.read_xml(shape)
        groups = p.rows(tree, b)
        self.assertEqual([r['raw_index'] for g in groups for r in g['rows'] if r['target']], [20,32])
        bad = copy.deepcopy(b)
        bad['metrics']['fsm'][p.SCOPE]['bits'] = format(int(bad['metrics']['fsm'][p.SCOPE]['bits'],16) | (1<<15), 'x')
        with self.assertRaises(Exception): p.rows(tree,bad)


if __name__ == '__main__': unittest.main()
