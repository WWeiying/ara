import unittest
from pathlib import Path
import re

import wave_profile as probe


class ProfileTest(unittest.TestCase):
    def test_all_control_signals_required_unique_no_payload_arrays(self):
        value = probe.profile()
        signals = value['signals']
        self.assertEqual(value['edge'], 'negedge')
        self.assertEqual(len(signals), len({row['alias'] for row in signals}))
        self.assertEqual(len(signals), len({row['path'] for row in signals}))
        self.assertTrue(all(row['required'] is True for row in signals))
        aliases = {row['alias'] for row in signals}
        for owner in ('qbs', 'akv'):
            for name in ('command_fire', 'terminal', 'range_fifo_count_q', 'burst_fifo_count_q',
                         'ar_stalled_q', 'completion_valid_q', 'fault_pending_q', 'plan_state_q'):
                self.assertIn(owner+'_'+name, aliases)
        for channel in ('ar', 'r', 'aw', 'w', 'b'):
            for slot in ('a_full_q', 'b_full_q'):
                self.assertIn('cut_'+channel+'_'+slot, aliases)
        self.assertNotIn('bank_rdata', str(value))

    def test_capture_is_bounded_but_does_not_quit_program(self):
        text = probe.script(20)
        self.assertIn('run 20ns\ndump -close\nrun\n', text)
        self.assertNotIn('quit', text)
        self.assertNotIn('-depth', text)
        self.assertEqual(text.count('dump -add'), len(probe.profile()['signals'])+1)
        for invalid in (0, -1, 500001, True, 1.5, '20ns'):
            with self.assertRaises(ValueError):
                probe.script(invalid)
        self.assertTrue(probe.script(20, capability_only=True).endswith('dump -close\nquit\n'))

    def test_profile_names_exist_in_current_source(self):
        root = Path(__file__).resolve().parents[3]
        sources = {
            'qbs': (root/'hardware/src/vlsu/qbs/qbs_engine.sv').read_text(),
            'akv': (root/'hardware/src/vlsu/akv/akv_engine.sv').read_text(),
            'reader': (root/'hardware/src/vlsu/qbs/qbs_read_engine.sv').read_text(),
            'activation': (root/'hardware/src/vlsu/qbs/qbs_activation_context.sv').read_text(),
            'vlsu': (root/'hardware/src/vlsu/vlsu.sv').read_text(),
            'slots': (root/'hardware/deps/common_cells/src/spill_register_flushable.sv').read_text(),
            'cut': (root/'hardware/deps/common_cells/src/spill_register.sv').read_text(),
            'tb': (root/'hardware/tb/ara_tb.sv').read_text()}
        for item in probe.profile()['signals']:
            path = item['path']
            if 'i_read_engine/' in path:
                source = sources['reader']
            elif 'i_activation_context/' in path:
                source = sources['activation']
            elif 'gen_spill_reg/' in path:
                source = sources['slots']
            elif 'i_axi_cut/' in path:
                source = sources['cut']
            elif 'i_qbs_engine/' in path:
                source = sources['qbs']
            elif 'i_akv_engine/' in path:
                source = sources['akv']
            else:
                source = sources['vlsu'] if 'i_vlsu/' in path else sources['tb']
            self.assertRegex(source, r'\b'+re.escape(path.rsplit('/',1)[1])+r'\b', item['alias'])


if __name__ == '__main__':
    unittest.main()
