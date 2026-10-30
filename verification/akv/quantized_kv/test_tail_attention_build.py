import unittest
from pathlib import Path
from unittest.mock import patch

import build_tail_attention as builder


class TailBuild(unittest.TestCase):
    def test_reject_unaccepted_or_mutated_gold(self):
        for document in ({}, {'state': 'FAIL'}, {'state': 'PASS', 'native_execution': True}):
            with patch.object(builder.s, 'read_json', return_value=document), self.assertRaises(ValueError):
                builder.checked_gold(Path('/synthetic'), 'q8_0')

    def test_actual_reference_receipt(self):
        directory = builder.ROOT / 'verification/out/akv-quantkv-tail-gold-20261024-01'
        for kind in ('q8_0', 'q4_0'):
            records, pins = builder.checked_gold(directory, kind)
            self.assertEqual(set(records), {5, 33})
            self.assertTrue(all(row['bytes'] == 6144 and row['elements'] == 1536 for row in records.values()))
            self.assertIn(str(directory / 'result.json'), pins)

    def test_score_export_and_original_arithmetic(self):
        source = (builder.HERE / 'attention_tail_main.c').read_text()
        self.assertIn('const unsigned prefixes[] = {5, 33}', source)
        self.assertIn('qbs_native_execute_command(opaque', source)
        self.assertIn('QUANT_TAIL_QK', source)
        self.assertIn('akv_quant_online_head_major(', source)
        self.assertIn('akv_quant_strided_execute(', source)
        self.assertNotIn('qbs_ref_execute', source)
        self.assertIn('fc != ordinary_flags', source)


if __name__ == '__main__':
    unittest.main()
