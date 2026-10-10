import unittest
import prove_fma_lzc_spare_disconnected as p


class SpareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=p.SOURCE.read_text()

    def test_complete_frozen_references(self):
        records=p.references(self.source);self.assertEqual(len(records),17)
        for width,spare in ((25,31),(51,63),(109,127)):
            result=p.prove(width,records)
            self.assertEqual(result['spare_index'],spare)
            self.assertEqual(result['all_read_indices'],[0,spare-1])

    def test_child_offbyone_reaches_spare_rejected(self):
        bad=self.source.replace('l * 2 + 1];','l * 2 + 2];')
        self.assertNotEqual(bad,self.source)
        for width in (25,51,109):
            with self.assertRaises(ValueError):p.prove(width,p.references(bad))

    def test_output_spare_read_rejected(self):
        records=p.references(self.source.replace('index_nodes[0]', 'index_nodes[31]'))
        with self.assertRaises(ValueError):p.prove(25,records)

    def test_whole_array_read_and_extra_assert_rejected(self):
        for bad in (self.source.replace('index_nodes[0]','index_nodes'),
                    self.source+'\nassert property (sel_nodes[31]);\n'):
            with self.assertRaises(ValueError):p.references(bad)

    def test_no_generic_eval_or_unknown_variables(self):
        for expression in ('unknown+1','f(1)','2**100','True','1/2'):
            with self.assertRaises(ValueError):p.arithmetic(expression,{})


if __name__=='__main__':unittest.main()
