import unittest
import measure_scalar_misalign791 as m


class Delta(unittest.TestCase):
    def test_only_new_bit_not_old_target_coordinates(self):
        a,g=m.merge_rows({'s':dict(width=4,checksum='1',bits='0xa')},{'s':dict(width=4,checksum='1',bits='0xc')})
        self.assertEqual(a['s']['bits'],'0xe');self.assertEqual(g['s']['new_directions'],1)
    def test_already_hit_has_no_gain(self):
        _,g=m.merge_rows({'s':dict(width=4,checksum='1',bits='0xf')},{'s':dict(width=4,checksum='1',bits='0xc')})
        self.assertEqual(g,{})
    def test_checksum_or_width_drift_rejected(self):
        for row in (dict(width=5,checksum='1',bits='0x0'),dict(width=4,checksum='2',bits='0x0')):
            with self.assertRaises(ValueError):m.merge_rows({'s':dict(width=4,checksum='1',bits='0x0')},{'s':row})
    def test_missing_scope_and_overflow_rejected(self):
        with self.assertRaises(ValueError):m.merge_rows({'s':dict(width=4,checksum='1',bits='0x0')},{})
        with self.assertRaises(ValueError):m.merge_rows({'s':dict(width=4,checksum='1',bits='0x0')},{'s':dict(width=4,checksum='1',bits='0x10')})


if __name__=='__main__':unittest.main()
