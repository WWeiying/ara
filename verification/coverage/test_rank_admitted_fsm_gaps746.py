import unittest
import xml.etree.ElementTree as ET
import rank_admitted_fsm_gaps746 as rank


class RankTests(unittest.TestCase):
    def test_native_records_only(self):
        record = ['1', '2', 'scope', 'machine', '3', 'why', 'Transition', 'A->B', '0->1']
        self.assertEqual(list(rank.exclusions({'a': [record], 'b': ['scope', 'Toggle']})),
                         [tuple(record)])

    def test_bitmap_left_to_right_and_native_identity(self):
        shape = ET.fromstring('<fsmdef><fsmfsm name="m" chksum="3">'
            '<state id="0" name="A"/><state id="1" name="B"/>'
            '<transition fromid="0" toid="1"/></fsmfsm></fsmdef>')
        result = rank.gaps('scope', dict(bits='0x4', width=3, checksum='1'), shape,
                           {('scope', 'm', '3', 'Transition', 'A->B')})
        self.assertEqual(result['remaining_states'], 1)
        self.assertEqual(result['remaining_transitions'], 0)
        self.assertEqual(result['missing'][0]['name'], 'B')
        with self.assertRaises(ValueError):
            rank.gaps('scope', dict(bits='0x10', width=3, checksum='1'), shape, set())

    def test_exact_admitted_population(self):
        result = rank.collect()
        self.assertEqual(result['population'], 746)
        self.assertFalse(result['official_percentages_recomputed'])
        self.assertTrue(result['instances'])


if __name__ == '__main__':
    unittest.main()
