import unittest
import calibrate_gap102_branch_path as m


class CalibrationTests(unittest.TestCase):
    def test_one_based_not_zero_based(self):
        vector="0"*285+"1"+"0"*(1270-286)
        self.assertEqual(m.expression_bit(vector,985),"1")
        self.assertEqual(vector[985],"0")
        self.assertEqual(vector[-1-985],"0")

    def test_zero_outside_indices_rejected(self):
        for index in (0,-1,1271,True):
            with self.assertRaises(ValueError):
                m.expression_bit("0"*1270,index)

    def test_endpoints(self):
        self.assertEqual(m.expression_bit("10",1),"0")
        self.assertEqual(m.expression_bit("10",2),"1")


if __name__ == "__main__":
    unittest.main()
