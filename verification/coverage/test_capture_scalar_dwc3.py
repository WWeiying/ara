import copy
import unittest
import capture_scalar_dwc3 as c


class NativeClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=c.life.read_bound(c.REVIEW,c.REVIEW_SHA)
        cls.cfg={'expected':c.expected(cls.r,'123')}

    def text(self,records):
        return '\n'.join('CHECKSUM: "'+r[0]+' '+r[1]+'"\nINSTANCE: '+r[2]+'\nFsm '+r[3]+' "'+r[4]+'"\nANNOTATION: "'+r[5]+'"\n'+r[6]+' '+r[7]+' "'+r[8]+'"' for r in records)+'\n'

    def test_state_absorbs_exact_two_arcs(self):
        rows=[r for r in self.cfg['expected'] if r[6]=='State']
        self.assertEqual(len(c.semantics(self.text(rows),self.cfg)),1)

    def test_three_explicit_and_order(self):
        self.assertEqual(c.semantics(self.text(self.cfg['expected']),self.cfg),
            c.semantics(self.text(self.cfg['expected'][::-1]),self.cfg))

    def test_missing_state(self):
        with self.assertRaises(ValueError):c.semantics(self.text([r for r in self.cfg['expected'] if r[6]!='State']),self.cfg)

    def test_duplicate(self):
        with self.assertRaises(ValueError):c.semantics(self.text(self.cfg['expected']*2),self.cfg)

    def test_all_identity_fields_protected(self):
        for i in range(9):
            with self.subTest(field=i):
                row=list(self.cfg['expected'][0]);row[i]+='x'
                with self.assertRaises(ValueError):c.semantics(self.text([row]),self.cfg)

    def test_extra_protected_state(self):
        row=list(next(r for r in self.cfg['expected'] if r[6]=='State'));row[7]='W_IDLE';row[8]='0'
        with self.assertRaises(ValueError):c.semantics(self.text(self.cfg['expected']+[row]),self.cfg)

    def test_all_read_machines_protected(self):
        groups=c.groups(self.r)
        self.assertEqual(sum(len(g['names']) for g in groups),31)
        self.assertTrue(all(not g['targets'] for g in groups if g['machine']!='w_state_d'))

    def test_real_source_reconstruction(self):
        self.assertEqual(c.proof.collect(),self.r)


if __name__=='__main__':unittest.main()
