import unittest
import cvxif_padding_native776_v2 as p
from test_cvxif_padding_native776 import config, compact_el


class EmptyScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.c=config();cls.text=compact_el(cls.c)

    def test_exact_roundtrip(self):self.assertEqual(len(p.parse_el(self.text,self.c)),18516)

    def header(self):
        i=self.c['instances'][0]
        return 'CHECKSUM: "'+i['design_module_checksum']+' '+i['toggle_checksum']+'"\nINSTANCE: '+i['scope']+'\n'

    def test_appended_empty_whole_scope_rejected(self):
        with self.assertRaises(ValueError):p.parse_el(self.text+self.header(),self.c)

    def test_prepended_empty_whole_scope_rejected(self):
        with self.assertRaises(ValueError):p.parse_el(self.header()+self.text,self.c)

    def test_annotation_only_scope_rejected(self):
        with self.assertRaises(ValueError):p.parse_el(self.text+self.header()+'ANNOTATION: "extra"\n',self.c)

    def test_unowned_checksum_rejected(self):
        with self.assertRaises(ValueError):p.parse_el(self.text+'CHECKSUM: "1 2"\n',self.c)

    def test_duplicate_instance_header_rejected(self):
        text=self.text.replace('INSTANCE: '+p.base.proof.SCOPE+'\n','INSTANCE: '+p.base.proof.SCOPE+'\nINSTANCE: '+p.base.proof.SCOPE+'\n',1)
        with self.assertRaises(ValueError):p.parse_el(text,self.c)

    def test_both_direction_candidate_accepted(self):
        self.assertEqual(len(p.parse_el(p.base.native.primitive.candidate(self.c),self.c)),18516)


if __name__=='__main__':unittest.main()
