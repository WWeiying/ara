from pathlib import Path
import unittest
from unittest.mock import patch

import summarize_common_attention as summary


class CompletedSummary(unittest.TestCase):
    def test_reject_incomplete_or_mutated_audit(self):
        for document in ({}, {'state': 'FAIL'}, {'state': 'INDEPENDENT_COMMON_ATTENTION_ACCEPTED'}):
            with patch.object(summary.s, 'read_json', return_value=document), self.assertRaises(ValueError):
                summary.checked_summary(Path('/synthetic/audit'))

    def test_family_identity_and_partial_scope(self):
        row = dict(kind='q8_0', variant='BOTH_RVV_DECODE')
        result = summary.combine([row])
        self.assertEqual(result['accepted_comparisons'], 1)
        self.assertEqual(len(result['missing_comparisons']), 5)
        self.assertFalse(result['complete_family'])
        self.assertFalse(result['cross_elf_cost_subtraction_supported'])
        for rows in ([], [row, row], [dict(row, kind='q8_K')]):
            with self.assertRaises(ValueError):
                summary.combine(rows)

    def test_full_family(self):
        rows = [dict(kind=kind, variant=variant) for kind in ('q4_0', 'q8_0') for variant in
                ('ORIGINAL_DECODERS', 'CANDIDATE_RVV_DECODE', 'BOTH_RVV_DECODE')]
        self.assertTrue(summary.combine(rows)['complete_family'])

    def test_table_does_not_round_or_relabel_cycles(self):
        row = dict(kind='q8_0', variant='BOTH_RVV_DECODE', ordinary_cycle_sum=2578265,
                   candidate_cycle_sum=1096039, speedup=2578265 / 1096039)
        text = summary.markdown(summary.combine([row]))
        self.assertIn('2,578,265', text)
        self.assertIn('1,096,039', text)
        self.assertIn('2.352348x', text)
        self.assertIn('not K gathering', text)
        self.assertIn('Missing entries are not classified', text)


if __name__ == '__main__':
    unittest.main()
