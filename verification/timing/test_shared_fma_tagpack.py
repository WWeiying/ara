import copy
import unittest
from run_shared_fma_tagpack_soc import compare


class ExactAcceptance(unittest.TestCase):
    def test_equal(self):
        row=dict(finish_time=100,hw_cycles=['20'],micro=[['dot','20','actual=1']],
                 lanes=[['lane0','1','100','10','10','4','0','3','3','4','0']])
        compare(row,copy.deepcopy(row))

    def test_reject_drift(self):
        row=dict(finish_time=100,hw_cycles=['20'],micro=[['dot','20','actual=1']],lanes=[['lane0']])
        for field in row:
            other=copy.deepcopy(row); other[field]=None
            with self.subTest(field=field),self.assertRaises(ValueError): compare(row,other)

    def test_missing_measurement(self):
        row=dict(finish_time=100,hw_cycles=['20'],micro=[],lanes=[])
        for field in row:
            other=copy.deepcopy(row); del other[field]
            with self.subTest(field=field),self.assertRaises(KeyError): compare(row,other)


if __name__=='__main__': unittest.main()
