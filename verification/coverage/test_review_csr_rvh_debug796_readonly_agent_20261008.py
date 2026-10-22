import unittest

import review_csr_rvh_debug796_readonly_agent_20261008 as review


class OwnershipTest(unittest.TestCase):
    def test_internal_parent_and_leaf(self):
        for name in ('dcsr_q', 'dcsr_q.xdebugver', 'dscratch0_d', 'htval_q'):
            self.assertTrue(review.target_conflict(dict(scope=review.SCOPE, directive='Toggle ' + name)))

    def test_observer_is_not_storage(self):
        self.assertFalse(review.target_conflict(dict(scope=review.SCOPE.rsplit('.', 1)[0],
                                                    directive='Toggle rvfi_probes_o.csr.dcsr_q.xdebugver')))

    def test_ancestor_hierarchical_object(self):
        self.assertTrue(review.target_conflict(dict(scope=review.SCOPE.rsplit('.', 1)[0],
                                                   directive='Toggle csr_regfile_i.dcsr_q.xdebugver')))

    def test_whole_scope_hold(self):
        self.assertTrue(review.target_conflict(dict(scope=review.SCOPE, directive='WHOLE_SCOPE')))

    def test_unrelated(self):
        self.assertFalse(review.target_conflict(dict(scope=review.SCOPE, directive='Toggle mstatus_q')))


if __name__ == '__main__':
    unittest.main()
