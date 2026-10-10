import unittest
import audit_toggle_stimulus769 as a


class ExclusionTests(unittest.TestCase):
    def test_real_multidimensional_encoding(self):
        fields,whole=a.exclusions('INSTANCE: x\nToggle gen_lzc.index_nodes [62:0][5:0] "logic [63:0][5:0]gen_lzc.index_nodes"\n')
        self.assertEqual(fields,{('x','gen_lzc.index_nodes')})
        self.assertFalse(whole)

    def test_reg_net_and_direction(self):
        fields,_=a.exclusions('INSTANCE: x\nToggle cur_rem "reg cur_rem[60:0]"\nToggle 0to1 y [0] "net y[1:0]"\n')
        self.assertEqual(fields,{('x','cur_rem'),('x','y')})

    def test_whole_ancestor_only(self):
        _,whole=a.exclusions('INSTANCE: x\nANNOTATION: observer\nINSTANCE: other\nFsm state_q "1"\n')
        self.assertTrue(a.overlaps('x.child','signal',{},whole))
        self.assertFalse(a.overlaps('xy','signal',{},whole))
        self.assertNotIn('other',whole)

    def test_field_overlap_not_other_scope(self):
        fields={'x':{'fp8[0].e'}}
        self.assertTrue(a.overlaps('x','fp8',fields,set()))
        self.assertFalse(a.overlaps('y','fp8',fields,set()))
        self.assertFalse(a.overlaps('x','fp16',fields,set()))

    def test_unknown_encoding_rejected(self):
        for text in ('Toggle bad "unknown bad"','Bogus all'):
            with self.assertRaises(ValueError):a.exclusions('INSTANCE: x\n'+text)

    def test_unscoped_record_rejected(self):
        with self.assertRaises(ValueError):a.exclusions('Toggle a "logic a"')


if __name__=='__main__':unittest.main()
