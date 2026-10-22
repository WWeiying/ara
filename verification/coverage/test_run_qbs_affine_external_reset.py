import unittest
from pathlib import Path
import run_qbs_affine_external_reset as runner


class ExactFixtureTests(unittest.TestCase):
    def test_exact_three_stage_mapping(self):
        self.assertEqual(runner.STAGES, {'aux': (1, 9), 'scale': (2, 16), 'min_scale': (3, 14)})
        for stage, (code, _) in runner.STAGES.items():
            c = runner.configuration(stage)
            self.assertEqual(c['ext_value'], code)
            self.assertEqual(c['ext_target'], runner.SCOPE + '.entry_state_q[0]')
            self.assertEqual(c['ext_guard'], runner.SCOPE + '.entry_valid_q[0]')
            self.assertEqual(len(c['ext_dump_objects']), len(set(c['ext_dump_objects'])))

    def test_unknown_stage_rejected(self):
        with self.assertRaises(ValueError):
            runner.configuration('dot;force DUT 1')

    def test_exact_elf_ucli_no_automatic_reset(self):
        cmd = runner.command('aux', Path('/tmp/case'))
        self.assertIn('+PRELOAD=' + str(runner.PRE / 'qbs_affine_slot0_cancel.elf'), cmd)
        self.assertIn('+NO_FSDB', cmd)
        self.assertIn('-ucli', cmd)
        self.assertFalse(any('RESET_ON_AXI' in x for x in cmd))

    def text(self, stage='aux'):
        c = runner.configuration(stage)
        return '\n'.join(['EXT_RESET_READY %s %d' % (c['ext_target'], c['ext_value']),
            'EXT_RESET_TARGET %s %d' % (c['ext_target'], c['ext_value']), 'EXT_RESET_ASSERT',
            *['EXT_RESET_LOW_EDGE %d' % e for e in range(1, 5)], 'EXT_RESET_RELEASE', 'EXT_RESET_DONE'])

    def test_complete_actual_marker_sequence(self):
        self.assertEqual(len(runner.markers(self.text(), 'aux')), 9)

    def test_echo_only_rejected(self):
        with self.assertRaises(ValueError):
            runner.markers('puts "' + self.text().replace('\n', '"\nputs "') + '"', 'aux')

    def test_missing_edge_rejected(self):
        with self.assertRaises(ValueError):
            runner.markers(self.text().replace('EXT_RESET_LOW_EDGE 3\n', ''), 'aux')

    def test_error_even_after_done_rejected(self):
        with self.assertRaises(ValueError):
            runner.markers(self.text() + '\nEXT_RESET_ERROR bad', 'aux')

    def test_wrong_phase_rejected(self):
        with self.assertRaises(ValueError):
            runner.markers(self.text('scale'), 'aux')

    def test_duplicate_reset_rejected(self):
        with self.assertRaises(ValueError):
            runner.markers(self.text() + '\n' + self.text(), 'aux')


if __name__ == '__main__':
    unittest.main()
