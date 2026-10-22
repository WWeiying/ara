import unittest

import review_rvv_restart_word_boundary768 as m


class BoundaryReview(unittest.TestCase):
    def test_exact_legal_lane_distribution_and_last_word(self):
        self.assertEqual([m.lane_start(508, i) for i in range(4)], [127]*4)
        self.assertEqual([m.lane_start(511, i) for i in range(4)], [128,128,128,127])
        self.assertEqual(127//4, 31)
        self.assertEqual(3 << (2*(127%4)), 0xc0)

    def test_illegal_restart_and_lane_rejected(self):
        for start, lane in [(-1,0), (512,0), (508,4)]:
            with self.assertRaises(ValueError): m.lane_start(start,lane)

    def test_actual_source_contract_and_negative_gate_mutation(self):
        import json
        texts, bindings = m.frozen_sources(json.loads(m.BOOK.read_bytes()))
        self.assertEqual(len(bindings),9)
        self.assertEqual(m.source_contract(texts)['vlmax'],512)
        for filename, old in [('lane_sequencer.sv','vfu_operation_d.vstart += 1\'b1;'),
                              ('vmfpu.sv','vfpu_control_in = issue_be;'),
                              ('ara_pkg.sv','MfpuInsnQueueDepth = 4;')]:
            changed=dict(texts); changed[filename]=changed[filename].replace(old,'removed')
            with self.assertRaises(ValueError): m.source_contract(changed)

    def test_independent_complete_destination_oracle(self):
        dest=[8]*512
        phases=[]
        for start in (508,511,0):
            for _ in range(4):
                dest=[v+8 if i>=start else v for i,v in enumerate(dest)]
            phases.append([dest[0],dest[508],dest[511]])
        self.assertEqual(phases,[[8,40,40],[8,40,72],[40,72,104]])
        self.assertTrue(all(v==40 for v in dest[:508]))
        self.assertEqual(dest[508:],[72,72,72,104])


if __name__=='__main__': unittest.main()
