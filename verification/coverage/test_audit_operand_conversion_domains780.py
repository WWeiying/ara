import unittest
import audit_operand_conversion_domains780 as a


class DomainTests(unittest.TestCase):
    def test_maskb_cross_format_rejected(self):
        self.assertIsNotNone(a.classify('mask_b', '5', ['OpQueueConversionSExt4', 'EW8']))

    def test_maskb_actual_move_retained(self):
        self.assertIsNone(a.classify('mask_b', '5', ['OpQueueConversionSExt4', 'EW16']))

    def test_alua_legal_narrow_retained(self):
        self.assertIsNone(a.classify('alu_a', '5', ['OpQueueConversionZExt2', 'EW8']))

    def test_no_unhit_implies_unreachable(self):
        self.assertIsNone(a.classify('alu_a', '6', ['operand_valid_o', 'SupportIntExt2']))

    def test_wrong_fu_candidate(self):
        self.assertIsNotNone(a.classify('alu_a', '4', ['cmd.is_reduct', 'MFPU_ADDRGEN']))

    def test_unknown_queue_rejected(self):
        with self.assertRaises(Exception):
            a.classify('mfpu_a', '5', ['OpQueueConversionWideFP2'])

    def test_ambiguous_vector_rejected(self):
        with self.assertRaises(Exception):
            a.classify('mask_b', '5', ['OpQueueConversionSExt2', 'OpQueueConversionSExt4'])


if __name__ == '__main__':
    unittest.main()
