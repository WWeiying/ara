import copy
import unittest
import xml.etree.ElementTree as ET

import audit_qbs_bank1_suffix793 as c


class SuffixAudit(unittest.TestCase):
    def fixture(self):
        nodes = [ET.Element('node', name='guard', type='1', portnode='3'),
                 ET.Element('vectornode', name='group_hit', left='31', right='0', type='3', portnode='0')]
        target = dict(attributes=dict(nodes[1].attrib), source_zero_bit_indices=[1,3],
                      actual_missing789_coordinates=[4,5,8,9])
        return nodes, dict(checksum='3028946256', width=66, bits='0x0'), {'group_hit':target}

    def test_full_field_zero_and_dynamic_port_not_waived(self):
        nodes,row,targets = self.fixture(); row['bits'] = hex(1 << 65)
        fields = c.fields(nodes,row,targets)
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0]['raw_serialized_directions'], '10')
        self.assertFalse(fields[0]['whole_object_exclusion'])
        self.assertEqual(fields[1]['candidate_raw_hit_coordinates'], [])

    def test_candidate_hit_is_explicit_counterexample_not_skip(self):
        nodes,row,targets = self.fixture(); row['bits'] = hex(1 << (65-4))
        fields = c.fields(nodes,row,targets)
        self.assertEqual(fields[1]['candidate_raw_hit_coordinates'], [4])

    def test_checksum_width_overflow_negatives(self):
        nodes,row,targets = self.fixture()
        for key,value in [('checksum','0'), ('width',65), ('bits',hex(1<<66)), ('width',False)]:
            with self.assertRaises(ValueError): c.fields(nodes,dict(row,**{key:value}),targets)

    def test_missing_duplicate_wrong_type_and_target_decl(self):
        nodes,row,targets = self.fixture()
        for mutated in (nodes[:-1], nodes+[nodes[1]], [nodes[0],ET.Element('arrays', **nodes[1].attrib)]):
            with self.assertRaises(ValueError): c.fields(mutated,row,targets)
        bad = copy.deepcopy(targets); bad['group_hit']['attributes']['type'] = '1'
        with self.assertRaises(ValueError): c.fields(nodes,row,bad)

    def test_partial_only_and_serialized_position_binding(self):
        nodes,row,targets = self.fixture()
        for field,value in [('source_zero_bit_indices',list(range(32))),
                            ('source_zero_bit_indices',[1,1]), ('actual_missing789_coordinates',[3,4,7,8])]:
            bad = copy.deepcopy(targets); bad['group_hit'][field] = value
            with self.assertRaises(ValueError): c.fields(nodes,row,bad)

    def test_exact792_prefix_no_reorder_duplicate_or_samecount_substitution(self):
        old = ['design']+['test%d'%i for i in range(792)]
        new = old+['slot793']; self.assertEqual(c.prefix(old,new), 'slot793')
        for bad in (old+['test0'], [old[1],old[0]]+old[2:]+['slot793'], old[:-1]+['foreign','slot793'], old):
            with self.assertRaises(ValueError): c.prefix(old,bad)


if __name__ == '__main__': unittest.main()
