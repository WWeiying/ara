import unittest
import capture_fsm124 as m


class Candidates(unittest.TestCase):
    def test_reset_no_never_added(self):
        for lane in range(4):
            for unit in ('i_vmfpu','i_valu'):
                scope='x.gen_lanes[%d].i_lane.i_vfus.%s' % (lane,unit)
                for source in ('INTER_LANES_REDUCTION_RX','INTER_LANES_REDUCTION_TX','INTRA_LANE_REDUCTION','LN0_REDUCTION_COMMIT'):
                    self.assertFalse(m.addition(scope,source,'NO_REDUCTION'))

    def test_pair_exact12(self):
        self.assertEqual(len(m.PAIR_ARCS)*2,12)
        self.assertFalse(m.addition(m.PAIR,'Send','Ready'))
        self.assertFalse(m.addition(m.PAIR,'Pending','Empty'))

    def test_port_reset_and_normal_paths_protected(self):
        self.assertEqual(len(m.PORT_ARCS),6)
        self.assertFalse(m.addition(m.PORT0,'REPLAY_REQ','IDLE'))
        self.assertFalse(m.addition(m.PORT0,'MISS_REQ','IDLE'))

    def test_lane0_ln0_not_added(self):
        self.assertFalse(m.addition('x.gen_lanes[0].i_vmfpu','LN0_REDUCTION_COMMIT','OSUM_REDUCTION'))

    def test_simd_never_added(self):
        self.assertFalse(m.addition('x.i_simd_div','ISSUE_SKIP','ISSUE_IDLE'))

    def test_exact_lane_additions(self):
        sources=('INTER_LANES_REDUCTION_RX','INTER_LANES_REDUCTION_TX','INTRA_LANE_REDUCTION','LN0_REDUCTION_COMMIT')
        destinations=('INTRA_LANE_REDUCTION','OSUM_REDUCTION','NO_REDUCTION')
        counts={}
        for unit in ('i_vmfpu','i_valu'):
            counts[unit]=sum(m.addition('x.gen_lanes[%d].%s' % (lane,unit),s,d)
                             for lane in range(4) for s in sources for d in destinations)
        self.assertEqual(counts,{'i_vmfpu':26,'i_valu':8})


if __name__=='__main__': unittest.main()
