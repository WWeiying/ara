import unittest
import rank_qbs_payload_hits766 as m


class Residual(unittest.TestCase):
    def fixture(self):
        return {'scope':dict(raw_width=4,checksum='1',records=[dict(classification='HOLD_MAPPING',missing_serialized_coordinates=[0,1])])}

    def test_actual_direction_is_removed(self):
        d=m.residual(self.fixture(),{'scope':dict(width=4,checksum='1',bits='0x8')})
        self.assertEqual(d['scope']['records'][0]['missing_serialized_coordinates'],[1])

    def test_shape_and_structural_counterexample_rejected(self):
        with self.assertRaises(ValueError):m.residual(self.fixture(),{'scope':dict(width=5,checksum='1',bits='0x0')})
        f=self.fixture();f['scope']['records'][0]['classification']='STRUCTURAL'
        with self.assertRaises(ValueError):m.residual(f,{'scope':dict(width=4,checksum='1',bits='0x8')})

    def test_covered_and_forbidden_commands_not_selected(self):
        matches={'scope':{'SIDE_DIRECT_METADATA':[1],'NEWER_MAIN_ISOLATED_INGRESS_HYPOTHESIS':[],
                         'OLDER_MAIN_PENDING_DRAIN_HYPOTHESIS':[]}}
        w=dict(kind='WEIGHT',profile='Q6_K',profile_enum=2,layout='ROW_MAJOR',phase=2,matches=matches)
        a=dict(kind='ACTIVATION',contexts=8,profile='Q8_K',phase=8,matches={'scope':{k:[] for k in matches['scope']}})
        self.assertEqual(m.select([w,a],4,{m.signature(w,a)})[0],[])
        commands,coords,_=m.select([w,a],4,set());self.assertEqual(len(commands),1);self.assertEqual(coords,{('scope',1)})


if __name__=='__main__':unittest.main()
