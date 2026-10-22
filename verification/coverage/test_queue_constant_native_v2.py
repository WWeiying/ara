import unittest
import queue_constant_native_v2 as v2

class SingleBit(unittest.TestCase):
    def setUp(self):
        self.ns=v2.namespace()
        self.c=dict(instances=[dict(scope='root.child',design_module_checksum='1',toggle_checksum='2',
            signals=[dict(name='read_pointer_q',bits=[0],scalar=False,left=0,right=0)])])
    def test_actual_collapsed_signature(self):
        text='CHECKSUM: "1 2"\nINSTANCE: root.child\nToggle read_pointer_q "logic read_pointer_q"\n'
        self.assertEqual(len(self.ns['parse_el'](text,self.c)),2)
    def test_exact_bit_zero_still_supported(self):
        self.assertEqual(len(self.ns['parse_el'](self.ns['candidate'](self.c),self.c)),2)
    def test_not_arbitrary_range_normalization(self):
        self.c['instances'][0]['signals'][0].update(left=3,bits=[0])
        with self.assertRaises(ValueError):
            self.ns['parse_el']('CHECKSUM: "1 2"\nINSTANCE: root.child\nToggle read_pointer_q "logic read_pointer_q"',self.c)

if __name__=='__main__':unittest.main()
