import unittest

import review_scoreboard_cause796_readonly_agent_20261008 as review


class CauseBoundaryTest(unittest.TestCase):
    def test_exact_mask_protects_interrupt_and_low_code(self):
        self.assertEqual(len(review.BITS), 57)
        self.assertEqual(review.MASK, 0x7fffffffffffffc0)
        self.assertEqual(review.MASK & ((1 << 63) | 63), 0)

    def test_sync_interrupt_and_fflags_bounds(self):
        for code in range(25):
            self.assertEqual(code & review.MASK, 0)
        for code in (1, 3, 5, 7, 9, 11, 12):
            self.assertEqual(((1 << 63) | code) & review.MASK, 0)
        self.assertEqual(31 & review.MASK, 0)
        self.assertNotEqual((1 << 16) & review.MASK, 0)

    def test_acc_and_shared_memory_are_not_independently_proven(self):
        for name in ('ex_i[4].cause', 'ex_ex_i[4].cause', 'mem_q[0].sbe.ex.cause',
                     'mem_n[7].sbe.ex.cause', 'fwd_o.sbe[2].ex.cause', 'commit_instr_o[0].ex.cause'):
            self.assertIsNone(review.independent_chain(name))

    def test_issue_copy_does_not_depend_on_mem(self):
        self.assertEqual(review.independent_chain('issue_instr_o[0].ex.cause'), 'PINNED_DECODE_ISSUE_COPY')
        self.assertIsNotNone(review.independent_chain('ex_i[3].cause'))

    def test_packed_parent_and_exact_leaf_ownership(self):
        for token in ('mem_q', 'mem_q[0].sbe.ex', 'mem_q[0].sbe.ex.cause'):
            self.assertTrue(review.ownership_conflict('s', 'mem_q[0].sbe.ex.cause',
                                                     dict(scope='s', directive='Toggle ' + token)))
        self.assertFalse(review.ownership_conflict('s', 'mem_q[0].sbe.ex.cause',
                                                  dict(scope='s', directive='Toggle mem_q[1].sbe.ex.cause')))

    def test_whole_ancestor_hold(self):
        self.assertTrue(review.ownership_conflict('s.child', 'ex_i[1].cause',
                                                 dict(scope='s', directive='WHOLE_SCOPE')))


if __name__ == '__main__':
    unittest.main()
