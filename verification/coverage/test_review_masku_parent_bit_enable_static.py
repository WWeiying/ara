import unittest
from xml.etree.ElementTree import Element

import review_masku_parent_bit_enable_static as m


class StaticTests(unittest.TestCase):
    def setUp(self):
        self.parent = (m.ROOT / 'hardware/src/masku/masku.sv').read_text()
        self.child = (m.ROOT / 'hardware/src/masku/masku_operands.sv').read_text()
        self.package = (m.ROOT / 'hardware/include/ara_pkg.sv').read_text()

    def test_actual_source(self):
        self.assertEqual(m.parent_contract(self.parent)['occurrence_lines'], [116, 155])
        m.prior.source_contract(self.child, self.parent, self.package)

    def test_new_read_or_driver(self):
        for tail in ('assign other = bit_enable_mask;', "assign bit_enable_mask = '1;",
                     'always_comb bit_enable_mask[0] = signal;'):
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                m.parent_contract(self.parent + '\n' + tail)

    def test_active_producer(self):
        with self.assertRaises(ValueError):
            m.prior.source_contract(self.child.replace('VlBitMaskEnable = 0', 'VlBitMaskEnable = 1'),
                                    self.parent, self.package)
        with self.assertRaises(ValueError):
            m.prior.source_contract(self.child.replace(' &= ', ' |= '), self.parent, self.package)

    def test_wrong_native_shape(self):
        attrs = dict(name=m.NAME, file='588', line_num='116', type='1', portnode='0',
                     excluded='0', left='255', right='0')
        m.validate_node(Element('vectornode', attrs))
        for key, value in [('portnode', '3'), ('type', '2'), ('left', '127'), ('right', '1'),
                           ('file', '558'), ('name', 'alu_result_compressed_seq')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_node(Element('vectornode', dict(attrs, **{key: value})))


if __name__ == '__main__':
    unittest.main()
