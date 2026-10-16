import unittest
from execution_order import efficient_order, reorder


class ExecutionOrderTests(unittest.TestCase):
    def test_returning_diagnostics_precede_known_stall_traces(self):
        cases=[dict(name='rvv_trace_fp_move_single_restart_e32_m4',sha256='move'),
               dict(name='rvv_trace_fault_replay_segment_nf2_e16_m1',sha256='fault'),
               dict(name='rvv_trace_extension_e16_m2',sha256='extension'),
               dict(name='rvv_detail_fp_compare_unmasked_e16_m1',sha256='compare'),
               dict(name='rvv_trace_permute_restart_e16_m1',sha256='permute'),
               dict(name='rvv_fp_move_restart_e64_m1',sha256='original')]
        before=[dict(c) for c in cases]
        order=efficient_order(cases)
        self.assertEqual(order,[cases[i]['name'] for i in (1,3,0,2,4,5)])
        self.assertEqual(cases,before)
        self.assertEqual({id(c) for c,_ in reorder([(c,None) for c in cases],order)},
                         {id(c) for c in cases})

    def test_preparation_reduction_precedes_original_stalls(self):
        cases=[dict(name='rvv_fp_move_restart_e32_m8'),
               dict(name='rvv_small_segments_misaligned_e64_m2'),
               dict(name='rvv_memory_restart_e8_m1')]
        self.assertEqual(efficient_order(cases),[cases[i]['name'] for i in (1,2,0)])

    def test_memory_mixed_outcomes_follow_diagnostics_without_mutation(self):
        cases = [dict(name='rvv_fp_move_restart_e32_m4', sha256='old'),
                 dict(name='rvv_memory_restart_e8_m8', sha256='memory8', timeout_seconds=300),
                 dict(name='rvv_small_fault_e8_m1_u0_s0_b1_m2', sha256='small'),
                 dict(name='rvv_memory_restart_e16_m1', sha256='memory16', timeout_seconds=300)]
        snapshot = [dict(c) for c in cases]
        order = efficient_order(cases)
        self.assertEqual(order, [cases[i]['name'] for i in (2, 1, 3, 0)])
        selected = reorder([(c, object()) for c in cases], order)
        self.assertEqual({id(c) for c, _ in selected}, {id(c) for c in cases})
        self.assertEqual(cases, snapshot)

    def test_slide_reductions_precede_full_originals(self):
        cases=[dict(name='rvv_fp_move_restart_e16_m4'),
               dict(name='rvv_small_slide_e8_m8_s0_m0',lmul='m8'),
               dict(name='rvv_prefix_slide_e16_m8_s0_m3',lmul='m8')]
        self.assertEqual(efficient_order(cases),[cases[i]['name'] for i in (1,2,0)])

    def test_ranking_and_stable_order(self):
        names = ['rvv_segment_alignment_e32_m1', 'a_e8_m8', 'b_e16_m1',
                 'rvv_fp_compare_restart_unmasked_e32_m8', 'c_e32_m2']
        cases = [dict(name=name, sha256=name) for name in names]
        order = efficient_order(cases)
        self.assertEqual(order, [names[3], names[2], names[4], names[1], names[0]])
        selected = [(case, object()) for case in cases]
        result = reorder(selected, order)
        self.assertEqual([case['name'] for case, _ in result], order)
        self.assertEqual({id(case) for case, _ in result}, {id(c) for c in cases})
        self.assertEqual([case['name'] for case in cases], names)

    def test_omissions_additions_and_duplicates_rejected(self):
        selected = [(dict(name='a'), None), (dict(name='b'), None)]
        for names in (['a'], ['a', 'c'], ['a', 'b', 'b']):
            with self.assertRaises(ValueError):
                reorder(selected, names)

    def test_empty(self):
        self.assertEqual(reorder([], efficient_order([])), [])

    def test_single_mask_diagnostics_precede_long_originals(self):
        cases = [dict(name='rvv_fixed_restart_e8_m4'),
                 dict(name='rvv_small_masks_scalar_restart_e8_m8', lmul='m8')]
        self.assertEqual(efficient_order(cases), [cases[1]['name'], cases[0]['name']])

    def test_short_diagnostics_precede_full_overlap_stalls_without_dropping_cases(self):
        cases = [dict(name='rvv_extension_e16_m2_vf2', overlap=True),
                 dict(name='rvv_prefix_fp_move_restart_e64_m8_ops4',lmul='m8'),
                 dict(name='rvv_repro_mask_boundary'),
                 dict(name='rvv_repro_whole_restart'),
                 dict(name='rvv_detail_fp_compare_restart_e64_m8',lmul='m8'),
                 dict(name='rvv_extension_e16_m2_vf2_ops0',overlap=True,operation_ids=[0])]
        order=efficient_order(cases)
        self.assertEqual(order,[cases[i]['name'] for i in (1,4,3,2,5,0)])
        result=reorder([(c,object()) for c in cases],order)
        self.assertEqual({id(c) for c,_ in result},{id(c) for c in cases})

    def test_partition_ranking_retains_exact_cases(self):
        cases = [
            dict(name='rvv_fp_move_restart_e16_m2_ops3', lmul='m2', operation_ids=[3]),
            dict(name='rvv_fp_move_restart_e32_m8_ops5', lmul='m8', operation_ids=[5]),
            dict(name='rvv_fp_move_restart_e32_m1_ops5', lmul='m1', operation_ids=[5]),
            dict(name='rvv_fp_move_restart_e64_m1_ops2', lmul='m1', operation_ids=[2]),
        ]
        order = efficient_order(cases)
        self.assertEqual(order, [cases[i]['name'] for i in (2, 1, 0, 3)])
        selected = [(case, object()) for case in cases]
        result = reorder(selected, order)
        self.assertEqual({id(case) for case, _ in result}, {id(case) for case in cases})
        self.assertEqual(cases[0]['operation_ids'], [3])

    def test_extension_overlap_follows_nonoverlap_m8(self):
        cases = [
            dict(name='rvv_extension_e16_m2_vf2_ops3', lmul='m2', operation_ids=[3]),
            dict(name='rvv_extension_e16_m8_vf2_ops0', lmul='m8', operation_ids=[0]),
            dict(name='rvv_extension_e16_m2_vf2_ops2', lmul='m2', operation_ids=[2]),
            dict(name='rvv_extension_e16_m8_vf2_ops1', lmul='m8', operation_ids=[1]),
        ]
        order = efficient_order(cases)
        self.assertEqual(order, [cases[i]['name'] for i in (1, 3, 0, 2)])
        self.assertEqual(len(set(order)), len(cases))

    def test_permutation_slide_family_risk_is_deferred_not_removed(self):
        cases = [
            dict(name='rvv_permute_restart_e8_m1_ops12',lmul='m1',operation_ids=[12]),
            dict(name='rvv_permute_restart_e32_m8_ops4',lmul='m8',operation_ids=[4]),
            dict(name='rvv_permute_restart_e8_m1_ops4',lmul='m1',operation_ids=[4]),
            dict(name='rvv_permute_restart_e64_m8_ops12',lmul='m8',operation_ids=[12]),
            dict(name='rvv_permute_restart_e8_m1_ops13',lmul='m1',operation_ids=[13]),
            dict(name='rvv_permute_restart_e8_m1_ops14',lmul='m1',operation_ids=[14]),
            dict(name='rvv_permute_restart_e8_m1_ops15',lmul='m1',operation_ids=[15]),
            dict(name='rvv_permute_restart_e8_m1_ops16',lmul='m1',operation_ids=[16]),
            dict(name='rvv_permute_restart_e8_m1_ops17',lmul='m1',operation_ids=[17]),
            dict(name='rvv_permute_restart_e8_m1_ops18',lmul='m1',operation_ids=[18]),
            dict(name='rvv_permute_restart_e8_m1_ops19',lmul='m1',operation_ids=[19]),
            dict(name='rvv_permute_restart_e8_m1_ops20',lmul='m1',operation_ids=[20]),
        ]
        order=efficient_order(cases)
        self.assertEqual(order,[cases[i]['name'] for i in (2,11,1,0,3,4,5,6,7,8,9,10)])
        result=reorder([(c,object()) for c in cases],order)
        self.assertEqual({id(c) for c,_ in result},{id(c) for c in cases})

    def test_wide_gather_family_preserves_every_case_after_ordinary_work(self):
        cases = [
            dict(name='rvv_permute_restart_e8_m4_ops0',lmul='m4',operation_ids=[0]),
            dict(name='rvv_permute_restart_e8_m4_ops4',lmul='m4',operation_ids=[4]),
            dict(name='rvv_permute_restart_e8_m8_ops20',lmul='m8',operation_ids=[20]),
            dict(name='rvv_permute_restart_e8_m8_ops4',lmul='m8',operation_ids=[4]),
            dict(name='rvv_permute_restart_e8_m2_ops0',lmul='m2',operation_ids=[0]),
            dict(name='rvv_permute_restart_e8_m4_ops12',lmul='m4',operation_ids=[12]),
        ]
        order=efficient_order(cases)
        self.assertEqual(order,[cases[i]['name'] for i in (4,0,1,2,3,5)])
        result=reorder([(c,object()) for c in cases],order)
        self.assertEqual({id(c) for c,_ in result},{id(c) for c in cases})

    def test_measured_e16_m8_shape_does_not_defer_all_m8_moves(self):
        cases = [
            dict(name='rvv_permute_restart_e16_m8_ops5',lmul='m8',operation_ids=[5]),
            dict(name='rvv_permute_restart_e32_m8_ops5',lmul='m8',operation_ids=[5]),
            dict(name='rvv_permute_restart_e64_m8_ops5',lmul='m8',operation_ids=[5]),
        ]
        order=efficient_order(cases)
        self.assertEqual(order,[cases[i]['name'] for i in (1,2,0)])
        self.assertEqual(set(order),{c['name'] for c in cases})
