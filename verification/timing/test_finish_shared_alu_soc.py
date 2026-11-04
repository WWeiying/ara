import unittest
import run_shared_alu_soc as api
from finish_shared_alu_soc import classify, ZERO_ALU_CASE
from test_shared_alu_soc import passing_log


class Classification(unittest.TestCase):
    def log(self):
        return (passing_log().replace('eval=1,2,3,4','eval=0,0,0,0')+
                '\nPASSED: /tests/vwiden_lmul4_edges.c!')

    def test_only_reviewed_non_alu_case(self):
        self.assertEqual(classify(api,self.log(),ZERO_ALU_CASE)['finish_time'],'100000')
        with self.assertRaises(ValueError): classify(api,self.log(),'rv64uv-ara-vadd')

    def test_requires_firmware_pass(self):
        with self.assertRaises(ValueError):
            classify(api,self.log().replace('PASSED:','OTHER:'),ZERO_ALU_CASE)

    def test_assertion_not_waived(self):
        with self.assertRaises(ValueError): classify(api,self.log()+'\nFatal: bad',ZERO_ALU_CASE)

    def test_lane_evidence_not_waived(self):
        with self.assertRaises(ValueError):
            classify(api,self.log().replace('lane3','lane2'),ZERO_ALU_CASE)

    def test_memory_only_case(self):
        log=self.log().replace('vwiden_lmul4_edges.c','vunit_vstart_edges.c')
        self.assertEqual(classify(api,log,'rv64uv-ara-vunit_vstart_edges')['finish_time'],'100000')

    def test_vadd_requires_real_work_and_timer(self):
        with self.assertRaises(ValueError): classify(api,self.log(),'vvaddint32')
        with self.assertRaises(ValueError): classify(api,passing_log(),'vvaddint32')
        self.assertEqual(classify(api,passing_log()+'\n[hw-cycles]: 123','vvaddint32')['hw_cycles'],['123'])


if __name__=='__main__': unittest.main()
