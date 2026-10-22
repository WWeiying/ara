import unittest
import explain_gap102_snapshot_path as e


class EvidenceTests(unittest.TestCase):
    def test_raw_bit_not_expression_index(self):
        record=dict(width=1215,bits=hex(1<<(1214-142)))
        self.assertTrue(e.hit(record,142))
        self.assertFalse(e.hit(record,127))
        with self.assertRaises(ValueError):e.hit(record,1215)

    def test_active_intersection_for_original_case(self):
        self.assertEqual(e.active_regs(8,2,0,129,8),[8,9,10,11,12])
        self.assertEqual(e.active_regs(12,1,0,129,4),[12,13,14])

    def test_nonzero_vstart_not_proven_impossible(self):
        self.assertEqual(e.active_regs(8,2,128,129,8),[12])
        self.assertEqual(e.active_regs(12,1,128,129,4),[14])
        self.assertEqual(e.active_regs(8,2,129,129,8),[])


if __name__=="__main__":unittest.main()
