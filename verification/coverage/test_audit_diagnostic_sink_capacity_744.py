import unittest

import audit_diagnostic_sink_capacity_744 as audit


class DiagnosticEvidenceTests(unittest.TestCase):
    def test_identifier_boundary_and_comment(self):
        text = '// probe_q\nprobe_q <= probe_q + 1;\nother_probe_q = 0;\n'
        self.assertEqual(audit.references(text, 'probe_q'),
                         [dict(line=2, text='probe_q <= probe_q + 1;')])

    def test_qualified_field_boundary(self):
        text = 'a.snapshot.vl = 1;\na.snapshot.vlmul = 2;\n'
        self.assertEqual(len(audit.references(text, 'a.snapshot.vl')), 1)

    def test_actual_frozen_shape_not_inferred_summary_capacity(self):
        result = audit.collect()
        self.assertEqual((result['total_objects'], result['total_bits'],
                          result['total_bit_directions']), (224, 5519, 11038))
        summary = next(g for g in result['groups'] if g['group'] == 'AKV_print_summary')
        self.assertEqual(summary['bits'], 0)
        self.assertEqual(len(summary['absent_from_toggle_shape']), 32)
        self.assertFalse(result['native_qualified'])
        self.assertFalse(result['application_approved'])
        self.assertFalse(result['EDA_started'])
        self.assertTrue(any('vinsn_retired_q' in s for s in result['protected']))


if __name__ == '__main__':
    unittest.main()
