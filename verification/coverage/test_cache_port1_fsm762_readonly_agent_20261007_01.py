"""Regression checks for the actual independent cache port1 audit artifact."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'verification/out/cache-port1-fsm762-readonly-audit-agent-20261007-02.json'


class ActualAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_bytes())

    def test_actual_evidence_pins(self):
        for path, sha in self.report['pins'].items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), sha)

    def test_full_compiled_bitmap(self):
        r = self.report
        self.assertEqual(r['population'], 762)
        self.assertTrue(r['formal760_coordinates_unchanged'])
        rows = r['full_compiled_coordinate_table']
        self.assertEqual([x['raw_position'] for x in rows], list(range(28)))
        self.assertEqual(''.join('1' if x['hit'] else '0' for x in rows),
                         format(int(r['raw_bitmap']['bits'], 16), '028b'))
        self.assertEqual(len([x for x in r['missing'] if x['kind'] == 'State']), 3)
        self.assertEqual(len([x for x in r['missing'] if x['kind'] == 'Transition']), 12)

    def test_no_blanket_waiver(self):
        r = self.report
        reset = [x for x in r['missing'] if x['classification'].startswith('RESET_ONLY')]
        self.assertEqual([x['name'] for x in reset], ['MISS_REQ->IDLE'])
        self.assertEqual(len([x for x in r['missing'] if x['classification'] ==
                             'LEGAL_CONDITIONAL_SOURCE_PATH']), 14)
        self.assertFalse(r['disabled_configuration_waiver_supported'])
        self.assertFalse(r['full_formal_reachability_proof'])
        for x in r['missing']:
            self.assertFalse(x['native_exclusion_qualified'])

    def test_shortest_scenario_exact_unhit_bins(self):
        r = self.report
        s = r['recommended_shortest_scenario']
        missing = {x['raw_position'] for x in r['missing']}
        targets = {x['raw_position'] for x in s['target_coordinates']}
        self.assertEqual(targets, {6, 7, 21, 23, 27})
        self.assertTrue(targets <= missing)
        self.assertEqual([x['next_state'] for x in s['cycles']],
                         ['READ', 'REPLAY_REQ', 'REPLAY_READ', 'MISS_REQ'])
        self.assertFalse(s['observed'])
        self.assertFalse(r['EDA_launched'])
        self.assertFalse(r['RTL_modified'])

    def test_source_drift_not_hidden(self):
        r = self.report
        self.assertFalse(r['whole_source_tree_matches_frozen_build'])
        self.assertEqual(r['pin_checks']['cache_port1_relevant_sources']['mismatches'], 0)
        drift = r['pin_checks']['frozen_build_sources']['drift']
        self.assertEqual(len(drift), 3)
        for entry in drift:
            self.assertNotEqual(entry['actual_sha256'], entry['expected_sha256'])
            self.assertNotIn(entry['path'], r['pins'])


if __name__ == '__main__':
    unittest.main()
