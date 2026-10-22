import unittest
import select_qbs_payload_matrix764 as s


class TestSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=s.life.read_bound(s.REPORT,s.REPORT_SHA)
    def test_actual_unique_union(self):
        commands,all_coords,side=s.select(self.report['ranking'])
        self.assertEqual((len(commands),len(all_coords),len(side)),(8,2820,1100))
        fresh={(t['scope'],t['raw_coordinate']) for c in commands for t in c['fresh_typed_coordinates']}
        self.assertEqual(fresh,all_coords)
        self.assertEqual(sum(c['incremental_mapping_directions'] for c in commands),2820)
        self.assertEqual(sum(c['incremental_side_metadata_directions'] for c in commands),1100)
    def test_correct_compatible_profile_layout(self):
        commands,_,_=s.select(self.report['ranking'])
        for c in commands:
            self.assertEqual(c['activation_profile'],'Q8_K')
            self.assertEqual(c['activation_layout'],'M8_INTERLEAVED')
            self.assertEqual(c['m'],8);self.assertEqual(c['n'],8)
        self.assertEqual({c['weight_profile'] for c in commands},{'Q3_K','Q6_K','Q2_K'})
        self.assertEqual({c['weight_layout'] for c in commands},{'ROW_MAJOR','R4_BLOCK_MAJOR'})
    def test_empty_or_duplicate_only_cannot_extend(self):
        with self.assertRaises(ValueError):s.select([],1)
        rows=[dict(kind='WEIGHT',profile='Q3_K',profile_enum=5,layout='ROW_MAJOR',phase=0,matches={'scope':{'SIDE_DIRECT_METADATA':[1]}}),
              dict(kind='ACTIVATION',profile='Q8_K',contexts=8,phase=0,matches={'scope':{'SIDE_DIRECT_METADATA':[]}})]
        with self.assertRaises(ValueError):s.select(rows,2)


if __name__=='__main__':unittest.main()
