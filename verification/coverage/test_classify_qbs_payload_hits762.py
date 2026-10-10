import unittest

import classify_qbs_payload_hits762 as p


class MappingTests(unittest.TestCase):
    def test_weight_boundaries(self):
        cases = [(1,15,(2,15)), (1,16,(0,0)), (2,16,(1,0)),
                 (2,48,(0,0)), (3,192,(2,0)), (4,96,(2,0)),
                 (7,80,(2,16)), (8,6,(0,0)), (9,2,(0,0))]
        for profile, offset, expected in cases:
            self.assertEqual(p.weight_location(profile, offset), expected)

    def test_activation_bijection(self):
        for scale, quant in ((4,256),(2,32)):
            size = scale+quant+(32 if quant == 256 else 0)
            for contexts in (1,4,8):
                result = [p.activation_target(i,contexts,scale,quant)
                          for i in range(contexts*size)]
                self.assertEqual(set(result), {(c,o) for c in range(contexts) for o in range(size)})
                self.assertEqual(len(result), len(set(result)))

    def test_side_intersection_is_only_older_half(self):
        name = 'gen_side_row[2].gen_activation_byte[35].hit'
        self.assertEqual(p.classify(name,15,set(),{})[0], 'OLD1792_INVARIANT_PROJECTION')
        self.assertEqual(p.classify(name,16,set(),{})[0], 'FINITE_MAPPING_IMPOSSIBLE_CANDIDATE')

    def test_pending_never_claims_timing_witness(self):
        name = 'gen_write_merge[0].gen_bank_plane[2].gen_bank_row[0].gen_byte_merge[0].hit'
        key, _, _ = p.identity(name, 2)
        self.assertEqual(p.classify(name,2,{key},{key:{'start':0}})[0], 'HOLD_PENDING_DRAIN_OWNERSHIP')

    def test_bad_compiled_name_and_bit_rejected(self):
        for name, bit in [('injected.hit',0), ('gen_side_row[0].gen_weight_byte[20].hit',0),
                          ('gen_side_row[0].gen_weight_byte[0].hit',32)]:
            with self.assertRaises(ValueError): p.identity(name,bit)

    def test_all_profiles_have_real_payload_witnesses(self):
        possible, witnesses = p.possible_hits(0)
        self.assertTrue(any(k[0]=='activation' and k[2]==0 for k in possible))
        for profile, size in enumerate(p.SIZES, 1):
            self.assertTrue(any(p.weight_location(profile, o)[0] != 2 for o in range(size)))
        self.assertTrue(witnesses)

    def test_old_induction_and_frozen_sources(self):
        payload = p.ROOT/'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'
        p.old.source_contract(payload.with_name('qbs_block_adapter.sv').read_text(),
                              payload.read_text(), payload.with_name('qbs_compute_engine.sv').read_text())
        self.assertEqual(p.old.induction_check()['transition_combinations_checked'],768)


if __name__ == '__main__': unittest.main()
