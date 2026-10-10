import copy
import unittest
import xml.etree.ElementTree as ET

import review_cvxif_padding776 as p


class PaddingTests(unittest.TestCase):
    def setUp(self):
        self.sources={f:(p.ROOT/f).read_text() for f in p.FILES}
        self.params=dict(NrLanes='4',AxiDataWidth='128',AxiAddrWidth='64',
                         AxiUserWidth='1',AxiIdWidth='5',AxiCoreIdWidth='4')

    def test_real_source_derives_sizes(self):
        self.assertEqual(p.source_contract(self.sources,self.params)['channel_widths'],
                         dict(ar=98,aw=104,w=146,r=136,b=7))

    def reject_mutation(self,file,old,new):
        changed=dict(self.sources)
        self.assertIn(old,changed[file]);changed[file]=changed[file].replace(old,new,1)
        with self.assertRaises(ValueError):p.source_contract(changed,self.params)

    def test_signed_struct_rejected(self):
        self.reject_mutation(p.FILES[4],'struct packed {','struct packed signed {')

    def test_arithmetic_cast_rejected(self):
        self.reject_mutation(p.FILES[6],"1024'(ara_axi_req.ar)","1024'(ara_axi_req.ar + 1)")

    def test_signed_cast_rejected(self):
        self.reject_mutation(p.FILES[6],"1024'(ara_axi_req.ar)","1024'($signed(ara_axi_req.ar))")

    def test_extra_mirror_writer_rejected(self):
        x=dict(self.sources);x[p.FILES[6]]+='\nassign cvxif.axi_ar_payload = 0;\n'
        with self.assertRaises(ValueError):p.source_contract(x,self.params)

    def test_interface_writer_rejected(self):
        x=dict(self.sources);x[p.FILES[7]]+='\nalways_comb axi_ar_payload = 0;\n'
        with self.assertRaises(ValueError):p.source_contract(x,self.params)

    def test_width_parameter_rejected(self):
        x=dict(self.params,AxiCoreIdWidth='5')
        with self.assertRaises(ValueError):p.source_contract(self.sources,x)

    def test_extra_channel_field_rejected(self):
        self.reject_mutation(p.FILES[4],'id_t              id;', 'id_t              id; logic extra;')

    def definition(self):
        d=ET.Element('tgldef',name='ara_cvxif_dut_bind',chksum='22');shape=ET.SubElement(d,'tglshape')
        for i,ch in enumerate(p.CHANNELS):
            ET.SubElement(shape,'vectornode',name='axi_'+ch+'_payload_i',left='1023',right='0',
                          type='1',portnode='2',file='610',line_num=str(41+i),excluded='0')
        ET.SubElement(shape,'node',name='axi_aw_ready_i',type='1')
        ET.SubElement(shape,'arrays',name='protected_array')
        return d

    def test_exact_objects_and_complete_complement(self):
        a,b,w=p.bind_scope(p.SCOPE,self.definition(),'22','11')
        self.assertEqual((len(a),len(b),w),(5,2,10242))
        self.assertEqual(b[-1]['kind'],'arrays')

    def test_wrong_typed_bounds_rejected(self):
        d=self.definition();d.find('tglshape')[0].set('left','1022')
        with self.assertRaises(ValueError):p.bind_scope(p.SCOPE,d,'22','11')

    def test_wrong_port_role_rejected(self):
        d=self.definition();d.find('tglshape')[0].set('portnode','0')
        with self.assertRaises(ValueError):p.bind_scope(p.SCOPE,d,'22','11')

    def test_wrong_checksum_rejected(self):
        with self.assertRaises(ValueError):p.bind_scope(p.SCOPE,self.definition(),'23','11')

    def target(self):
        return dict(scope=p.SCOPE,name='axi_ar_payload_i',bits=list(range(98,1024)),
                    checksum='22',module_checksum='11')

    def el(self,directive,checksum='11 22',scope=p.SCOPE):
        return 'CHECKSUM: "'+checksum+'"\nINSTANCE: '+scope+'\n'+directive+'\n'

    def test_exact_directional_difference(self):
        text=self.el('Toggle 0to1 axi_ar_payload_i [1023:1020] "net axi_ar_payload_i[1023:0]"')
        got=p.existing_overlap(text,[self.target()])
        self.assertEqual(got,{(p.SCOPE,'axi_ar_payload_i',b,'0to1') for b in range(1020,1024)})

    def test_low_payload_not_duplicate(self):
        text=self.el('Toggle axi_ar_payload_i [97:0] "net axi_ar_payload_i[1023:0]"')
        self.assertFalse(p.existing_overlap(text,[self.target()]))

    def test_whole_parent_explicitly_overlaps(self):
        got=p.existing_overlap(self.el('',scope=p.SCOPE.rsplit('.',1)[0]),[self.target()])
        self.assertEqual(len(got),1852)

    def test_foreign_checksum_rejected(self):
        text=self.el('Toggle axi_ar_payload_i "net axi_ar_payload_i[1023:0]"','11 23')
        with self.assertRaises(ValueError):p.existing_overlap(text,[self.target()])

    def test_unknown_selector_rejected(self):
        text=self.el('Toggle axi_ar_payload_i [*] "net axi_ar_payload_i[1023:0]"')
        with self.assertRaises(ValueError):p.existing_overlap(text,[self.target()])

    def test_wrong_native_decl_rejected(self):
        text=self.el('Toggle axi_ar_payload_i [100] "reg axi_ar_payload_i[1023:0]"')
        with self.assertRaises(ValueError):p.existing_overlap(text,[self.target()])


if __name__=='__main__':unittest.main()
