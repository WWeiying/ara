import unittest
import rank_cva6_residual768 as r


class DomainTests(unittest.TestCase):
    def test_owners(self):
        self.assertEqual(r.domain('cpu.ex_stage_i.lsu_i.i_load_unit'), 'OTHER_OWNER_LSU_PTW_CACHE')
        self.assertEqual(r.domain('cpu.csr_regfile_i'), 'OTHER_OWNER_CSR_RVFI')
        self.assertEqual(r.domain('cpu.issue_stage_i.i_scoreboard'), 'SCOREBOARD')
        self.assertEqual(r.domain('cpu.i_frontend.i_instr_queue'), 'FETCH')

    def test_exception_and_address_not_auto_waived(self):
        for name in ('mem_q[0].sbe.ex.tval', 'mem_q[0].sbe.ex.cause', 'mem_n[0].sbe.ex.tinst'):
            self.assertEqual(r.classify(name), 'EXCEPTION_RETAIN_UNLESS_COMPLETE_PRODUCER_PROOF')
        self.assertEqual(r.classify('mem_q[0].sbe.pc'), 'ADDRESS_RETAIN_NO_OBSERVED_RANGE_WAIVER')

    def test_vset_bound_not_all_result(self):
        self.assertEqual(r.classify('preview_data_q'), 'VSET_BOUND_CANDIDATE_REQUIRES_ARCH_PRODUCER_PROOF')
        self.assertEqual(r.classify('mem_q[0].sbe.result'), 'SOURCE_REVIEW_REQUIRED')


if __name__ == '__main__': unittest.main()
