import unittest
import queue_constant_native as q

class ExactBits(unittest.TestCase):
    def setUp(self):
        self.c=dict(instances=[dict(scope='root.child',design_module_checksum='1',toggle_checksum='2',
            signals=[dict(name='operand_queue_cmd_i.conv',bits=[2],scalar=False,left=3,right=0),
                     dict(name='flush_i',bits=[0],scalar=True,left=0,right=0)])])
        self.text=q.candidate(self.c)
    def test_both_directions(self):self.assertEqual(len(q.parse_el(self.text,self.c)),4)
    def test_reject_whole_conv(self):
        with self.assertRaises(ValueError):q.parse_el(self.text.replace(' [2]',''),self.c)
    def test_reject_other_bit(self):
        with self.assertRaises(ValueError):q.parse_el(self.text.replace('[2]','[3]'),self.c)
    def test_reject_missing_direction(self):
        with self.assertRaises(ValueError):q.parse_el('\n'.join(x for x in self.text.splitlines() if '1to0' not in x),self.c)
    def test_reject_parent_scope(self):
        with self.assertRaises(ValueError):q.parse_el(self.text.replace('root.child','root'),self.c)
    def test_native_signature(self):
        text=self.text.replace('conv [2]','conv [2] "logic operand_queue_cmd_i.conv[3:0]"')
        self.assertEqual(q.parse_el(text,self.c),q.parse_el(self.text,self.c))
    def test_known_zero_conv_domain(self):
        self.assertTrue(all((x>>2)&1==0 for x in (0,1,2,8)))
        self.assertTrue(all((x>>2)&1==1 for x in (4,5,6,7)))

if __name__=='__main__':unittest.main()
