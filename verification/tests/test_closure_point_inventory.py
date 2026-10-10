#!/usr/bin/env python3
import sys
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import closure_point_inventory as inventory


class PointTests(unittest.TestCase):
    def test_line_explicit_not_xml_order(self):
        node = ET.fromstring('<linedef><linebb id="8" index="2"/><linebb id="5" index="0"/></linedef>')
        self.assertEqual([p['raw_index'] for p in inventory.points('line', node, 3)], [0, 2])

    def test_duplicate_line_index_rejected(self):
        node = ET.fromstring('<linedef><linebb index="0"/><linebb index="0"/></linedef>')
        with self.assertRaises(ValueError):
            inventory.points('line', node, 2)

    def test_out_of_range_line_rejected(self):
        with self.assertRaises(ValueError):
            inventory.points('line', ET.fromstring('<linedef><linebb index="2"/></linedef>'), 2)

    def test_branch_reversed_inside_each_group(self):
        node = ET.fromstring('<branch_def><branch_spec id="1" totalbranches="2">'
            '<branch_expr id="12" exprstr="a"/><branch_vector id="9"/><branch_vector id="4"/>'
            '</branch_spec><branch_spec id="2" totalbranches="1"><branch_vector id="7"/>'
            '</branch_spec></branch_def>')
        result = inventory.points('branch', node, 3)
        self.assertEqual([(p['raw_index'], p['native_id'], p['vector']) for p in result],
                         [(0, '1', '4'), (1, '1', '9'), (2, '2', '7')])

    def test_branch_malformed_group_rejected(self):
        node = ET.fromstring('<branch_def><branch_spec totalbranches="2"><branch_vector id="0"/></branch_spec></branch_def>')
        with self.assertRaises(ValueError):
            inventory.points('branch', node, 2)

    def condition(self, ids=(1, 2)):
        return ET.fromstring('<conddef><condspec file="1" lines="42">' + ''.join(
            '<expr_monitored condregid="%d" exprstr="x"><truth_table nrows="2" ncols="1" vecs="01"/>'
            '</expr_monitored>' % n for n in reversed(ids)) + '</condspec></conddef>')

    def test_condition_sorted_registers_reversed_rows(self):
        result = inventory.points('cond', self.condition(), 4)
        self.assertEqual([(p['native_id'], p['vector']) for p in result],
                         [('1', '1'), ('1', '0'), ('2', '1'), ('2', '0')])

    def test_condition_noncontiguous_rejected(self):
        with self.assertRaises(ValueError):
            inventory.points('cond', self.condition((1, 3)), 4)

    def test_condition_duplicate_id_rejected(self):
        with self.assertRaises(ValueError):
            inventory.points('cond', self.condition((1, 1)), 4)

    def test_condition_width_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            inventory.points('cond', self.condition(), 3)

    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValueError):
            inventory.points('fsm', self.condition(), 4)

    def test_scope_boundary(self):
        self.assertTrue(inventory.selected('x.queue.child', {'x.queue'}))
        self.assertTrue(inventory.selected('x.queue', {'x.queue'}))
        self.assertFalse(inventory.selected('x.queue2', {'x.queue'}))

    def test_definition_id_and_checksum_both_required(self):
        root = ET.fromstring('<root><conddef id="1" chksum="2"/><conddef id="3" chksum="2"/></root>')
        self.assertEqual(inventory.definition(root, ET.fromstring('<module id="3"/>'), '2').get('id'), '3')
        with self.assertRaises(ValueError):
            inventory.definition(root, ET.fromstring('<module id="4"/>'), '2')

    def test_ambiguous_definition_rejected(self):
        root = ET.fromstring('<root><conddef id="1" chksum="2"/><conddef id="1" chksum="2"/></root>')
        with self.assertRaises(ValueError):
            inventory.definition(root, ET.fromstring('<module id="1"/>'), '2')

    def test_absent_instance_checksum_is_not_inferred(self):
        self.assertIsNone(inventory.metric_checksum(None, None))

    def test_info_checksum_used_when_data_inherits(self):
        self.assertEqual(inventory.metric_checksum(None, '42'), '42')

    def test_data_checksum_used_when_info_absent(self):
        self.assertEqual(inventory.metric_checksum('42', None), '42')

    def test_conflicting_metric_checksums_rejected(self):
        with self.assertRaises(ValueError):
            inventory.metric_checksum('42', '43')


if __name__ == '__main__':
    unittest.main()
