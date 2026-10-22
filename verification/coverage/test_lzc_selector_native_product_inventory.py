"""Native inventory data parser and completeness boundary tests."""
import copy
import unittest

from lzc_selector_native_product_inventory import bind, decode_lines


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.static = dict(targets=[dict(scope='child', parameters=dict(WIDTH=10, MODE=1),
            module_checksum='3250293308')], protected=[dict(scope='child', metric='branch', points=[{}, {}]),
            dict(scope='child', metric='cond', points=[dict(expression='selector', vector=v,
                attributes=dict(optype='23')) for v in ('0', '1')])])
        self.records = [['population', 'design', 'dirs', ' '.join('test'+str(i) for i in range(707))],
            ['child_binding', 'child', '3250293308', 'MODE=1,WIDTH=10'],
            ['branch', 'child', '901', '0', 'Item901', 'Branch901.0', 'raw'],
            ['branch', 'child', '901', '1', 'Item901', 'Branch901.1', 'raw'],
            ['conditions', 'child', 'selector'],
            ['condition', 'child', 'selector', '0 1', 'raw', 'raw'],
            ['condition_ids_display', 'child', 'raw', 'raw'],
            ['child_complete', 'child', '2', '2']]

    def test_native_ids_observed_no_inference(self):
        result = bind(self.records, self.static)[0]
        self.assertEqual(result['branch_native_ids_observed'], ['901'])
        self.assertIsNone(result['conditions'][0]['native_id'])

    def test_foreign_checksum_missing_false_and_collateral_rejected(self):
        for kind in ('checksum', 'false', 'extra', 'foreign'):
            rows = copy.deepcopy(self.records)
            if kind == 'checksum':
                rows[1][2] = '438741478'
            elif kind == 'false':
                rows[5][3] = '1'
            elif kind == 'extra':
                rows.append(rows[2])
            else:
                rows[2][1] = 'parent'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                bind(rows, self.static)

    def test_tcl_data_is_parsed_not_evaluated(self):
        rows = decode_lines('condition child {[error should_not_execute]} {0 1} raw raw\n')
        self.assertEqual(rows[0][2], '[error should_not_execute]')

    def test_opaque_ui_bytes_and_quoted_newlines_preserved(self):
        rows = decode_lines('condition child selector {0 1} {opaque\x85bytes\nmore} raw\n')
        self.assertEqual(rows[0][4], 'opaque\x85bytes\nmore')
        with self.assertRaises(ValueError):
            decode_lines('condition child {unclosed\n')


if __name__ == '__main__':
    unittest.main()
