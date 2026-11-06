import unittest

from matrix_dot_pair import candidate_vectors
from matrix_engine_pair import adapt_wrapper,adapt_bench,pair
from test_projection_resources import VECTOR


def log(wide):
    return f'''MATRIX_ENGINE_CONFIG wide={wide}
QBS configuration response_gap=3 context_suite=0
QBS end-to-end case 0 PASS profile=1 M=4 N=4 Kb=1 layouts=2/2 cycles={200 if wide else 264}
QBS traffic case=0 weight=576 activation=1168 payload=1760 ranges=3 dot={64 if wide else 128} prefetch_wait=0
QBS engine PASS: 1 functional cases
'''


class MatrixEngineTests(unittest.TestCase):
    def test_functional_pair(self):
        measured=pair(log(0),log(1),VECTOR,candidate_vectors(VECTOR),3,0,True)
        self.assertEqual(measured['direct'][0]['ratio'],1.32)

    def test_reject_incomplete(self):
        for old,new in (('wide=1','wide=0'),('cycles=200','cycles=0'),('dot=64','dot=128'),
                        ('payload=1760','payload=1776'),('PASS: 1','PASS: 2'),('response_gap=3','response_gap=0')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                pair(log(0),log(1).replace(old,new),VECTOR,candidate_vectors(VECTOR),3,0,True)
        with self.assertRaises(ValueError):
            pair(log(0),log(1),VECTOR,candidate_vectors(VECTOR),3,0,False)

    def test_adapters_are_parameter_only(self):
        wrapper="    parameter bit SeedRestoreEnable = 1'b0,\n    .SeedRestoreEnable(SeedRestoreEnable),"
        result=adapt_wrapper(wrapper)
        self.assertIn('.WideMatrixDot(WideMatrixDot)',result)
        with self.assertRaises(ValueError):adapt_wrapper(wrapper+wrapper)
        bench='module qbs_engine_tb;\n  qbs_engine_composed #('
        self.assertIn('.WideMatrixDot(Wide)',adapt_bench(bench))
        with self.assertRaises(ValueError):adapt_bench(bench+bench)


if __name__=='__main__':unittest.main()
