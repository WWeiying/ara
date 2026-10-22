import unittest
import xml.etree.ElementTree as ET
import gap113_toggle_candidates as p


class Tests(unittest.TestCase):
    def test_prefix_stops_before_unknown_array(self):
        root = ET.fromstring('<tgldef><tglshape><node name="a" excluded="0"/>'
            '<vectornode name="b" left="3" right="0" excluded="0"/><arrays name="unknown"/>'
            '<node name="after"/></tglshape></tgldef>')
        rows, width = p.prefix(root)
        self.assertEqual(width, 10); self.assertEqual([r['signal'] for r in rows], ['a', 'b'])

    def test_both_directions_zero_not_direction_guess(self):
        root = ET.fromstring('<tgldef><tglshape><node name="a" excluded="0"/>'
            '<vectornode name="b" left="1" right="0" excluded="0"/></tglshape></tgldef>')
        rows, _ = p.prefix(root)
        missing = p.missing(rows, '000011')
        self.assertEqual(missing[0]['both_direction_zero_pairs'], [0])
        self.assertEqual(missing[1]['both_direction_zero_pairs'], [0])
        self.assertFalse(missing[1]['fully_uncovered_vector'])
        self.assertEqual(p.missing(rows, '011011'), [])

    def test_short_shape_and_excluded_rejected_or_protected(self):
        root = ET.fromstring('<tgldef><tglshape><node name="a" excluded="1"/></tglshape></tgldef>')
        rows, _ = p.prefix(root); self.assertEqual(p.missing(rows, '00'), [])
        with self.assertRaises(ValueError): p.missing(rows, '0')


if __name__ == '__main__': unittest.main()
