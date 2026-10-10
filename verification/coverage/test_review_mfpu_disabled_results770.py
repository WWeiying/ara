import unittest
import review_mfpu_disabled_results770 as m


class DisabledResults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts={p.name:p.read_text() for p in [m.ROOT/'hardware/src/lane/vmfpu.sv',
            m.ROOT/'hardware/deps/fpnew/src/fpnew_pkg.sv',m.ROOT/'hardware/deps/fpnew/src/fpnew_top.sv',
            m.ROOT/'hardware/deps/fpnew/src/fpnew_opgroup_block.sv',m.ROOT/'hardware/deps/common_cells/src/rr_arb_tree.sv']}

    def test_actual_source_and_padding_tree(self):
        m.source_contract(self.texts)
        self.assertEqual(m.lemma.constant_nodes(6,set(),m.MAX),{0:0,1:m.MAX,2:0,3:m.MAX,4:m.MAX,5:m.MAX,6:0})
        self.assertEqual(m.lemma.constant_nodes(6,{0,1,2},m.MAX),{2:0,5:m.MAX,6:0})

    def test_active_result_symbols_not_assumed_constant(self):
        self.assertNotIn(0,m.lemma.constant_nodes(6,{0},m.MAX))
        self.assertNotIn(3,m.lemma.constant_nodes(6,{0,1,2},m.MAX))

    def test_wrong_literal_request_driver_or_arbiter_rule_rejected(self):
        for file,old,new in [('fpnew_pkg.sv',"DONT_CARE = 1'b1","DONT_CARE = 1'bx"),
            ('fpnew_opgroup_block.sv',"assign fmt_out_valid[fmt] = 1'b0;","assign fmt_out_valid[fmt] = in_valid_i;"),
            ('rr_arb_tree.sv',"assign data_nodes[Idx0]  = DataType'('0);","assign data_nodes[Idx0]  = data_i[0];")]:
            texts=dict(self.texts);texts[file]=texts[file].replace(old,new)
            with self.assertRaises(ValueError):m.source_contract(texts)

    def test_unit_config_and_format_orientation_rejected(self):
        texts=dict(self.texts);texts['vmfpu.sv']=texts['vmfpu.sv'].replace("'{default: DISABLED}","'{default: MERGED}")
        with self.assertRaises(ValueError):m.source_contract(texts)
        texts=dict(self.texts);texts['fpnew_pkg.sv']=texts['fpnew_pkg.sv'].replace('[0:NUM_FP_FORMATS-1]       fmt_logic_t','[NUM_FP_FORMATS-1:0]       fmt_logic_t')
        with self.assertRaises(ValueError):m.source_contract(texts)

    def test_ports_flags_tags_storage_scalar_and_active_format_not_selected(self):
        scope=(m.PARENT%0)+'.gen_operation_groups[0].i_opgroup_block'
        for name in ('fmt_outputs[0].result','fmt_outputs[3].status.NV','fmt_outputs[3].tag.operand_a','result_o','fmt_out_valid'):
            self.assertIsNone(m.rule(scope,name))
        self.assertIsNone(m.rule(scope+'.i_arbiter','gen_arbiter.rr_q'))
        self.assertIsNone(m.rule('ara_tb.dut.scalar.i_fpnew.gen_operation_groups[4].i_opgroup_block','fmt_outputs[0].result'))
        self.assertEqual(m.rule(scope,'fmt_outputs[3].result')[0],m.MAX)


if __name__=='__main__':unittest.main()
