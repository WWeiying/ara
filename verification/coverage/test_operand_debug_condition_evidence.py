"""Read-only checks of the frozen 690-test condition inventory evidence."""
import hashlib
import json
from pathlib import Path
import unittest

from inventory_operand_debug import ROOT, REGIONS, SOURCE, SOURCE_SHA


class ConditionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads((ROOT / 'verification/out/'
            'operand-debug-condition-inventory-690-20261006-01.json').read_bytes())
        cls.bitmap = json.loads((ROOT / 'verification/out/'
            'gap83-offline-admitted-690-20261006-02/combined-bits.json').read_bytes())

    def test_inputs_are_still_exactly_pinned(self):
        for name, expected in self.evidence['input_sha256'].items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), expected)
        self.assertEqual(self.evidence['input_sha256'][str(SOURCE)], SOURCE_SHA)

    def test_inventory_does_not_authorize_exclusion(self):
        self.assertFalse(self.evidence['native_qualified'])
        self.assertEqual(self.evidence['status'], 'DEBUG_CONDITION_INVENTORY_ONLY_NO_EXCLUSIONS')
        for row in self.evidence['points']:
            self.assertEqual(row['decision'], 'REVIEW_REQUIRED_NOT_WAIVED')

    def test_regions_and_uniqueness(self):
        self.assertEqual(self.evidence['source_regions'], [list(r) for r in REGIONS])
        keys = set()
        for row in self.evidence['points']:
            point = row['point']
            self.assertTrue(point['line'].isdigit())
            self.assertTrue(any(a <= int(point['line']) <= z for a, z in REGIONS))
            key = (row['scope'], point['raw_index'])
            self.assertNotIn(key, keys)
            keys.add(key)
        self.assertEqual(len({r['scope'] for r in self.evidence['points']}), 4)

    def test_actual_bitmap_hits_and_checksums(self):
        unhit = 0
        for row in self.evidence['points']:
            record = self.bitmap['metrics']['cond'][row['scope']]
            index = row['point']['raw_index']
            self.assertEqual(row['metric'], 'cond')
            self.assertEqual(row['metric_checksum'], record['checksum'])
            self.assertGreaterEqual(index, 0)
            self.assertLess(index, record['width'])
            hit = bool(int(record['bits'], 16) & (1 << (record['width'] - index - 1)))
            self.assertEqual(row['hit'], hit)
            unhit += not hit
        self.assertEqual(self.evidence['counts'], dict(
            condition_positions=len(self.evidence['points']), condition_unhit=unhit))


if __name__ == '__main__':
    unittest.main()
