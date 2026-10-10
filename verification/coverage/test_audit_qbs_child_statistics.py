import unittest

import audit_qbs_child_statistics as audit


class ChildStatisticsTests(unittest.TestCase):
    def test_extra_product_reader_rejected(self):
        with self.assertRaises(Exception):
            audit.check_references('x <= x + 1;\nif (x) ready = 0;', 'x', ['x <= x + 1;'])

    def test_identifier_boundary_and_whitespace(self):
        refs = audit.check_references('// x\nother_x = 0;\nx  <=  x + 1;', 'x', ['x <= x + 1;'])
        self.assertEqual(len(refs), 1)

    def test_wrong_producer_rejected(self):
        with self.assertRaises(Exception):
            audit.check_references('x <= y + 1;', 'x', ['x <= x + 1;'])

    def test_frozen_compiled_whole_fields(self):
        result = audit.collect()
        self.assertEqual((result['total_objects'], result['total_bits'],
                          result['total_directions']), (15, 399, 798))
        self.assertFalse(result['application_approved'])
        self.assertFalse(result['native_qualified'])
        self.assertFalse(result['EDA_started'])
        self.assertTrue(all(g['all_other_objects_protected'] for g in result['groups']))


if __name__ == '__main__':
    unittest.main()
