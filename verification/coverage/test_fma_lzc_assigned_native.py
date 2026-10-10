import copy
import unittest
import fma_lzc_assigned_native as n


def config():
    signals=[]
    for name,dims,select in (('index_lut',[[24,0],[4,0]],[[24,0],[4,0]]),('in_tmp',[[24,0]],[[24,0]]),
                             ('sel_nodes',[[31,0]],[[30,0]]),('index_nodes',[[31,0],[4,0]],[[30,0],[4,0]])):
        signals.append(dict(name='gen_lzc.'+name,dimensions=dims,selected_dimensions=select))
    return dict(instances=[dict(scope='top.lzc',design_module_checksum='12',toggle_checksum='34',signals=signals)])


class RangeTests(unittest.TestCase):
    def test_exact_assigned_builder(self):
        c=config();self.assertEqual(len(n.parse_el(n.candidate(c),c)),672)

    def test_whole_index_nodes_forbidden(self):
        c=config();text=n.candidate(c).replace('gen_lzc.index_nodes [30:0][4:0]','gen_lzc.index_nodes')
        with self.assertRaises(ValueError):n.parse_el(text,c)

    def test_spare_selector_or_index_row_forbidden(self):
        c=config();text=n.candidate(c)
        for bad in (text.replace('sel_nodes [30:0]','sel_nodes [31:0]'),text.replace('index_nodes [30:0]','index_nodes [31:0]')):
            with self.assertRaises(ValueError):n.parse_el(bad,c)

    def test_flattening_wrong_inner_bounds_and_direction_missing(self):
        c=config();text=n.candidate(c)
        for bad in (text.replace('index_nodes [30:0][4:0]','index_nodes [154:0]'),
                    text.replace('index_nodes [30:0][4:0]','index_nodes [30:0][3:0]'),
                    text.replace('Toggle gen_lzc.in_tmp','Toggle 0to1 gen_lzc.in_tmp')):
            with self.assertRaises(ValueError):n.parse_el(bad,c)

    def test_signature_ports_checksum_duplicate(self):
        c=config();text=n.candidate(c)
        for bad in (text.replace('12 34','12 35'),text+'Toggle in_i [24:0] "logic in_i[24:0]"\n',
                    text.replace('logic gen_lzc.index_nodes[31:0][4:0]','logic gen_lzc.index_nodes[30:0][4:0]'),
                    text+'Toggle gen_lzc.in_tmp [24:0] "logic gen_lzc.in_tmp[24:0]"\n'):
            with self.assertRaises(ValueError):n.parse_el(bad,c)

    def test_native_separate_word_rows_equal_coordinates(self):
        c=config();text=n.candidate(c);whole='Toggle gen_lzc.index_nodes [30:0][4:0] "logic gen_lzc.index_nodes[31:0][4:0]"'
        rows='\n'.join('Toggle gen_lzc.index_nodes ['+str(row)+'][4:0] "logic gen_lzc.index_nodes[31:0][4:0]"' for row in range(31))
        self.assertEqual(n.parse_el(text,c),n.parse_el(text.replace(whole,rows),c))


if __name__=='__main__':unittest.main()
