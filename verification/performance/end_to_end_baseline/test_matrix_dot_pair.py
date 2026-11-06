import unittest

from matrix_dot_pair import candidate_vectors,counts,pair
from test_projection_resources import LOG,VECTOR


class MatrixDotTests(unittest.TestCase):
    def shape(self,profile,m,n=8,kb=3):return dict(profile=profile,m=m,n=n,k_blocks=kb)

    def test_wide_and_tail(self):
        self.assertEqual(counts(self.shape(1,4),True),dict(dot=384,capacity=24576))
        self.assertEqual(counts(self.shape(1,5),True)['dot'],576)
        self.assertEqual(counts(self.shape(1,6),True)['dot'],768)
        self.assertEqual(counts(self.shape(1,7),True)['dot'],768)
        self.assertEqual(counts(self.shape(1,8),True)['dot'],768)

    def test_preserve_short_and_decode(self):
        for profile,m in ((1,1),(1,2),(3,4),(6,4),(8,8),(9,3)):
            s=self.shape(profile,m)
            self.assertEqual(counts(s,True)['dot'],counts(s,False)['dot'])
            self.assertEqual(counts(s,True)['capacity'],2*counts(s,False)['capacity'])

    def test_pair(self):
        wide=candidate_vectors(VECTOR)
        self.assertIn('C 1 576 1168 4096 4096 64 96 16',wide)
        candidate=LOG.replace('dot=128','dot=64')
        self.assertEqual(len(pair(LOG,candidate,VECTOR,wide)),1)
        with self.assertRaises(ValueError):pair(LOG,candidate,VECTOR,wide.replace('576','577'))
        with self.assertRaises(ValueError):pair(LOG,candidate.replace('cast_aux=16','cast_aux=15'),VECTOR,wide)


if __name__=='__main__':unittest.main()
