import copy
import unittest
import operand_mask_data_02_toggle_delta as m


class TypedDeltaTests(unittest.TestCase):
    def test_exact_gain_no_lost_hit(self):
        old={'scope':dict(width=4,checksum='9',bits='0x5')}
        gains=m.merge(old,{'scope':dict(width=4,checksum='9',bits='0xa')})
        self.assertEqual(gains[0]['new_raw_positions'],2)
        self.assertEqual(old['scope']['bits'],'0xf')

    def test_shape_negative(self):
        old={'scope':dict(width=4,checksum='9',bits='0x5')}
        for rows in ({},{'scope':dict(width=5,checksum='9',bits='0')},
                     {'scope':dict(width=4,checksum='8',bits='0')},
                     {'scope':dict(width=4,checksum='9',bits='0x10')}):
            with self.assertRaises(ValueError):m.merge(copy.deepcopy(old),rows)


if __name__=='__main__':unittest.main()
