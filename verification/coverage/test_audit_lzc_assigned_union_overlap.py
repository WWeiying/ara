import unittest
import audit_lzc_assigned_union_overlap as r


class OwnershipTests(unittest.TestCase):
    def test_pair_directions_keep_exact_instance_owner(self):
        scopes,fields=r.ownership('INSTANCE: root.child[2]\nToggle 0to1 gen_lzc.sel_nodes [1] "logic gen_lzc.sel_nodes[31:0]"\nToggle 1to0 gen_lzc.sel_nodes [1] "logic gen_lzc.sel_nodes[31:0]"\n')
        self.assertEqual(scopes,{'root.child[2]'})
        self.assertEqual(fields,{('root.child[2]','gen_lzc.sel_nodes')})

    def test_same_field_other_instance_not_overlap(self):
        _,a=r.ownership('INSTANCE: root.a\nToggle gen_lzc.in_tmp "logic gen_lzc.in_tmp[24:0]"\n')
        _,b=r.ownership('INSTANCE: root.b\nToggle gen_lzc.in_tmp "logic gen_lzc.in_tmp[24:0]"\n')
        self.assertFalse(a&b)

    def test_unbound_toggle_rejected(self):
        with self.assertRaises(ValueError):r.ownership('Toggle foo "logic foo"\n')


if __name__=='__main__':unittest.main()
