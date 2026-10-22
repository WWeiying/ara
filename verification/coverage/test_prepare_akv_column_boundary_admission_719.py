import unittest

import prepare_akv_column_boundary_admission_719 as p


class AdmissionPreparationTest(unittest.TestCase):
    def test_left_to_right_raw_index_not_XML_vector_ID(self):
        row = dict(width=166,checksum="131544421",bits=hex(1<<141))
        self.assertTrue(p.raw_hit(row,24))
        self.assertFalse(p.raw_hit(row,4))

    def test_gain_mapping_independent_OR(self):
        before = dict(width=4,checksum="x",bits="0x4")
        after = dict(width=4,checksum="x",bits="0xd")
        self.assertEqual(p.gain_indices(before,after),[0,3])

    def test_no_gain_not_fabricated(self):
        row = dict(width=4,checksum="x",bits="0xf")
        self.assertEqual(p.gain_indices(row,row),[])

    def test_shape_change_rejected(self):
        with self.assertRaises(ValueError):
            p.gain_indices(dict(width=4,checksum="x",bits="0"),dict(width=4,checksum="y",bits="0"))

    def test_width_overflow_rejected(self):
        with self.assertRaises(ValueError):
            p.gain_indices(dict(width=4,checksum="x",bits="0"),dict(width=4,checksum="x",bits="0x10"))

    def test_raw_boolean_not_accepted_as_integer(self):
        with self.assertRaises(ValueError): p.raw_hit(dict(width=4,bits="0"),True)

    def test_admission_hard_block_no_full_scalar(self):
        with self.assertRaisesRegex(ValueError,"ADMISSION_BLOCKED"):
            p.admission_gate()


if __name__ == "__main__":
    unittest.main()
