import unittest

from review_board_return import command_budget,grouping


class BoardReviewTest(unittest.TestCase):
    def test_bounded_commands_and_tails(self):
        rows=[dict(op_name='MUL_MAT',name='ffn_gate-0',ne=[64,1,1,1]),
              dict(op_name='MUL_MAT',name='result_output',ne=[65,1,1,1])]
        self.assertEqual(command_budget(rows,32),5)
        self.assertEqual(command_budget(rows,64),3)
        self.assertEqual(grouping(rows[0]),'FFN_projection')
        self.assertEqual(grouping(rows[1]),'vocabulary_projection')

    def test_does_not_claim_prefill_command_halving(self):
        with self.assertRaises(ValueError):
            command_budget([dict(op_name='MUL_MAT',ne=[64,4,1,1])],64)
        with self.assertRaises(ValueError):
            command_budget([],64)


if __name__=='__main__':
    unittest.main()
