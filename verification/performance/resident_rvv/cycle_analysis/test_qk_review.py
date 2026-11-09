import copy
import unittest
import qk_review as q


class QkWorkTests(unittest.TestCase):
    def test_exact_real_work_and_tail(self):
        g=q.geometry((64,64,9))
        self.assertEqual(g['lane_fma_beats'],[4608,4352,4352,4352])
        self.assertEqual(g['lane_fma_elements'],[8960,8704,8704,8704])
        self.assertEqual(g['mean_lane_fma_beats'],4416)
        self.assertEqual(g['current_mapping_issue_floor'],4608)
        self.assertEqual(g['useful_fma_elements'],35072)
        self.assertEqual(g['masked_simd_slots'],256)

    def test_all_bounded_shapes_and_inactive_lanes(self):
        for d in (64,96,128):
            for h in (1,2):
                for t in range(1,65):
                    g=q.geometry((t,),d,h)
                    self.assertEqual(sum(g['tiles'][0]['local_elements']),t)
                    self.assertEqual(g['useful_fma_elements'],t*d*h)
                    self.assertEqual(g['busiest_lane_fma_beats'],((t+7)//8)*d*h)
                    self.assertTrue(all(b==0 for n,b in zip(g['tiles'][0]['local_elements'],
                        g['lane_fma_beats']) if n==0))

    def test_invalid_geometry(self):
        for args in (((),),((0,),),((65,),),((9,),63),((9,),128,3),((9,),128,2,8)):
            with self.assertRaises(ValueError): q.geometry(*args)

    def fixture(self):
        g=q.geometry((64,64,9))
        rows={str(l):dict(qk=dict(fma_input_handshakes=g['lane_fma_beats'][l],
            fma_destination_byte_enable_elements=g['lane_fma_elements'][l],
            fp_input_handshakes=g['lane_fma_beats'][l],cycles=9901)) for l in range(4)}
        return dict(state='ACCEPTED_PROBES_ANALYZED',hardware_optimization_measured=False,
            scope='host fixture only',lanes=rows,phases=dict(qk=dict(cycles=9901,
            lane_totals=dict(fma_input_handshakes=17664,fma_destination_byte_enable_elements=35072),
            akv=dict(command_fires=96,terminals=96,axi_ar_handshakes=0,
                     context_conflict_cycles=0,replay_request_denied_cycles=0))))

    def test_reject_average_substitution_and_bad_totals(self):
        q.review(self.fixture())
        for change in ('average','elements','total','transport'):
            d=copy.deepcopy(self.fixture())
            if change=='average': d['lanes']['0']['qk']['fma_input_handshakes']=4416
            if change=='elements': d['lanes']['0']['qk']['fma_destination_byte_enable_elements']-=1
            if change=='total': d['phases']['qk']['lane_totals']['fma_input_handshakes']-=1
            if change=='transport': d['phases']['qk']['akv']['axi_ar_handshakes']=1
            with self.assertRaises(ValueError): q.review(d)


if __name__=='__main__': unittest.main()
