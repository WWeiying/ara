import unittest
import xml.etree.ElementTree as ET
import prove_fpnew_tied_fields781 as p


class Proof(unittest.TestCase):
    def test_actual_callers(self):
        declaration = (p.m.ROOT/p.EXTRA[2]).read_text()
        for rel in p.EXTRA[:2]:
            p.rounding_guard((p.m.ROOT/rel).read_text(), declaration)

    def test_dynamic_id_rejected(self):
        with self.assertRaises(ValueError):
            p.rounding_guard("fpnew_rounding #(.X(1)) i_fpnew_rounding (.id_i (hart_id));",
                             'input logic [33:0] id_i')

    def test_id_width_rejected(self):
        with self.assertRaises(ValueError):
            p.rounding_guard("fpnew_rounding #(.X(1)) i_fpnew_rounding (.id_i ('0));",
                             'input logic [32:0] id_i')

    def test_ascending_formats(self):
        d = ET.Element('tgldef', name='Width=64,FpFmtMask=56,NUM_FORMATS=6,TagType=vfpu_tag_t )')
        for fmt in (3,4): p.disabled_guard(d, fmt)
        d.set('name', d.get('name').replace('FpFmtMask=56','FpFmtMask=60'))
        with self.assertRaises(ValueError): p.disabled_guard(d,3)

    def test_tag_type_rejected(self):
        d = ET.Element('tgldef', name='Width=64,FpFmtMask=56,NUM_FORMATS=6,TagType=logic )')
        with self.assertRaises(ValueError): p.disabled_guard(d,4)

    def test_role_and_width(self):
        n = ET.Element('vectornode', left='33', right='0', portnode='2')
        self.assertEqual(p.typed_guard(n,'id_i'),34)
        n.set('portnode','0')
        with self.assertRaises(ValueError): p.typed_guard(n,'id_i')

    def test_source_literal_mutation(self):
        texts = {p.Path(rel).name:(p.m.ROOT/rel).read_text() for rel in p.m.SOURCE}
        p.m.semantic_proof(texts)
        texts['fpnew_pkg.sv'] = texts['fpnew_pkg.sv'].replace("localparam logic DONT_CARE = 1'b1;",
                                                                "localparam logic DONT_CARE = 1'b0;")
        with self.assertRaises(ValueError): p.m.semantic_proof(texts)


if __name__ == '__main__': unittest.main()
