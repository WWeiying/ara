from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
import review_masku_vl_constant770 as m


class SourceProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=(m.ROOT/'hardware/src/masku/masku_operands.sv').read_text()
        cls.parent=(m.ROOT/'hardware/src/masku/masku.sv').read_text()
        cls.pkg=(m.ROOT/'hardware/include/ara_pkg.sv').read_text()

    def test_actual_complete_drivers(self):
        p=m.source_contract(self.text,self.parent,self.pkg);self.assertEqual(len(p['all_writes']),9)

    def test_enabled_or_overridable_configuration_rejected(self):
        for change in (self.text.replace('VlBitMaskEnable = 0','VlBitMaskEnable = 1'),
                       self.text.replace('localparam int unsigned VlBitMaskEnable','parameter int unsigned VlBitMaskEnable')):
            with self.assertRaises(ValueError):m.source_contract(change,self.parent,self.pkg)

    def test_ungated_nonzero_driver_rejected(self):
        for change in (self.text.replace('if (VlBitMaskEnable) begin','if (vinsn_issue_i.vm) begin',1),
                       self.text.replace("deshuffled_vl_bit_mask = '0;","deshuffled_vl_bit_mask = '1;",1),
                       self.text.replace("shuffled_vl_bit_mask = '0;","shuffled_vl_bit_mask = masku_operand_m_seq_o;",1),
                       self.text.replace('endmodule',"always_comb deshuffled_vl_bit_mask[0] = 1'b1;\nendmodule")):
            with self.assertRaises(ValueError):m.source_contract(change,self.parent,self.pkg)

    def test_parent_override_and_geometry_rejected(self):
        with self.assertRaises(ValueError):m.source_contract(self.text,self.parent.replace('.NrLanes  ( NrLanes   )','.NrLanes  ( 8 )'),self.pkg)
        with self.assertRaises(ValueError):m.source_contract(self.text,self.parent,self.pkg.replace('ELEN  = 64','ELEN  = 32'))

    def test_port_partial_shape_and_wrong_field_rejected(self):
        node=ET.Element('vectornode',dict(name=m.TARGETS[0],portnode='0',excluded='0',type='1',left='255',right='0'))
        m.validate_node(node,m.TARGETS[0])
        for key,value in [('portnode','3'),('left','127'),('right','1'),('excluded','1'),('name','bit_enable_mask_o')]:
            bad=ET.Element(node.tag,dict(node.attrib,**{key:value}))
            with self.assertRaises(ValueError):m.validate_node(bad,m.TARGETS[0])
        with self.assertRaises(ValueError):m.validate_node(node,'bit_enable_mask_o')

    def test_prepared_partial_and_whole_ancestor_block(self):
        text='INSTANCE: '+m.SCOPE+'\nCHECKSUM: 1400516067\nToggle 0to1 deshuffled_vl_bit_mask [255:0] "logic deshuffled_vl_bit_mask"\n'
        fields,whole=m.prior.exclusions(text)
        self.assertTrue(m.prior.overlaps(m.SCOPE,m.TARGETS[0],{m.SCOPE:{n for s,n in fields}},whole))
        self.assertTrue(m.prior.overlaps(m.SCOPE,m.TARGETS[1],{}, {m.SCOPE.rsplit('.',1)[0]}))


if __name__=='__main__':unittest.main()
