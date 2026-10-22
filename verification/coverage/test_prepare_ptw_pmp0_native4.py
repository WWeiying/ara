import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import prepare_ptw_pmp0_native4 as m


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = json.loads(m.INVENTORY.read_bytes())

    def test_exact_logical_inventory_no_guessed_native_ids(self):
        rows = m.logical_rows(self.saved)
        self.assertEqual(len(rows), 35)
        self.assertEqual([r['diagnostic_raw_index'] for r in rows if r['target']], [2, 10, 11, 16])
        self.assertTrue(all(r['native_selector'] is None and r['native_signature'] is None for r in rows))
        self.assertTrue(all(not rows[i]['target'] for i in (12, 14, 20, 21, 25, *range(26, 35))))

    def test_duplicate_raw_offset_rejected(self):
        saved = copy.deepcopy(self.saved)
        saved['protected'][0]['raw_index'] = 2
        with self.assertRaises(ValueError):
            m.logical_rows(saved)

    def test_hit_target_rejected(self):
        saved = copy.deepcopy(self.saved)
        saved['candidates'][0]['raw_hit'] = True
        with self.assertRaises(ValueError):
            m.logical_rows(saved)

    def test_transition_endpoint_mismatch_rejected(self):
        saved = copy.deepcopy(self.saved)
        saved['candidates'][1]['destination'] = 'PTE_LOOKUP'
        with self.assertRaises(ValueError):
            m.logical_rows(saved)

    def test_hstage_cannot_be_promoted(self):
        saved = copy.deepcopy(self.saved)
        saved['protected'][-1]['candidate'] = True
        with self.assertRaises(ValueError):
            m.logical_rows(saved)

    def test_exact_forwarding_not_unrelated_occurrence(self):
        good = 'cva6 #(.CVA6Cfg(CVA6Cfg), .T(foo)) i_ariane();'
        self.assertEqual(m.forwarding(good, 'cva6', 'i_ariane', 'CVA6Cfg')['instance'], 'i_ariane')
        for bad in (good.replace('CVA6Cfg(CVA6Cfg)', 'CVA6Cfg(other)'),
                    good.replace('i_ariane', 'other'), good + good,
                    'other #(.CVA6Cfg(CVA6Cfg)) x(); cva6 #(.CVA6Cfg(other)) i_ariane();'):
            with self.assertRaises(ValueError):
                m.forwarding(bad, 'cva6', 'i_ariane', 'CVA6Cfg')

    def test_actual_forwarding_and_preserved_keyword_boundaries(self):
        text = (m.ROOT / 'hardware/src/ara_system.sv').read_text()
        self.assertEqual(m.forwarding(text, 'cva6', 'i_ariane', 'CVA6Cfg')['expression'], 'CVA6Cfg')
        self.assertEqual(m.forwarding('end\ncva6 #(.CVA6Cfg(CVA6Cfg)) i_ariane();',
                                     'cva6', 'i_ariane', 'CVA6Cfg')['instance'], 'i_ariane')
        with self.assertRaises(ValueError):
            m.forwarding('badcva6 #(.CVA6Cfg(CVA6Cfg)) i_ariane();', 'cva6', 'i_ariane', 'CVA6Cfg')

    def test_expected_pin_conflict_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'evidence'
            path.write_bytes(b'original')
            pins = {}
            m.read_bound(path, pins)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                m.read_bound(path, pins)
            link = Path(name) / 'alias'
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                m.read_bound(link, {})

    def test_real_tcl_help_only_no_exclusion_calls(self):
        with tempfile.TemporaryDirectory() as name:
            prefix = 'set env(DVE_COVERAGE_OUTPUT) {%s}\n' % name
            prefix += 'proc help {command} {return "HELP $command"}\nproc gui_exit {args} {}\n'
            result = subprocess.run(['tclsh'], input='if {[catch {\n' + prefix + m.HOOK.read_text() +
                                    '\n} message]} {puts stderr $message; exit 1}\n',
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stderr, '')
            self.assertIn('PTW_FSM_HELP_ONLY_NOT_NATIVE_QUALIFICATION', result.stdout)
            text = (Path(name) / 'ptw-fsm-api-help.txt').read_text()
            self.assertEqual(text.count('HELP_STATUS 0'), 8)
            self.assertNotIn('gui_exclusion -', m.HOOK.read_text())


if __name__ == '__main__':
    unittest.main()
