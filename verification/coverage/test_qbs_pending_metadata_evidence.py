"""Revalidate source-bound candidate coordinates against historical692, read-only."""
import hashlib
import json
from pathlib import Path
import unittest
from inventory_operand_debug import ROOT


class QbsMetadataEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((ROOT / 'verification/out/'
            'qbs-pending-metadata-inventory-690-20261006-01.json').read_bytes())
        cls.calibration = json.loads((ROOT / 'verification/out/'
            'qbs-side-path-semantics-20261006-01.json').read_bytes())
        cls.bitmap = json.loads((ROOT / 'verification/out/'
            'gap85-offline-admitted-692-20261006-01/combined-bits.json').read_bytes())

    def test_all_inventory_and_calibration_inputs_unchanged(self):
        for pins in (self.inventory['input_sha256'], self.calibration['pins']):
            for name, expected in pins.items():
                self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), expected)

    def test_not_an_exclusion_approval(self):
        self.assertFalse(self.inventory['native_qualified'])
        self.assertFalse(self.inventory['waivers_applied'])
        self.assertFalse(self.calibration['native_DVE_qualified'])
        self.assertFalse(self.calibration['processor_coverage_added'])

    def test_latest_population_exact(self):
        self.assertEqual(len(self.bitmap['tests']), 692)
        self.assertEqual(len(set(self.bitmap['tests'])), 692)

    def test_unhit_candidates_still_zero_and_are_older_paths(self):
        targets = []
        for row in self.inventory['points']:
            if row['hit']:
                continue
            record = self.bitmap['metrics']['branch'][row['scope']]
            self.assertEqual(record['checksum'], row['metric_checksum'])
            self.assertEqual(row['point']['native_vector']['vector'], '0101')
            index = row['point']['raw_index']
            self.assertGreaterEqual(index, 0)
            self.assertLess(index, record['width'])
            self.assertFalse(int(record['bits'], 16) & (1 << (record['width'] - index - 1)))
            targets.append((row['scope'], index))
        self.assertEqual(len(targets), 448)
        self.assertEqual(len(set(targets)), 448)

    def test_all_hit_neighbor_paths_are_retained_and_still_hit(self):
        retained = []
        for row in self.inventory['points']:
            if not row['hit']:
                continue
            self.assertEqual(row['decision'], 'RETAIN_HIT')
            self.assertIn(row['point']['native_vector']['vector'], ('1000', '0011'))
            record = self.bitmap['metrics']['branch'][row['scope']]
            self.assertEqual(record['checksum'], row['metric_checksum'])
            index = row['point']['raw_index']
            self.assertTrue(int(record['bits'], 16) & (1 << (record['width'] - index - 1)))
            retained.append((row['scope'], index))
        self.assertEqual(len(retained), 896)
        self.assertEqual(len(set(retained)), 896)


if __name__ == '__main__':
    unittest.main()
