import unittest

import prove_qbs_even_start_hits762 as p


class EvenStart(unittest.TestCase):
    def test_page_burst_head_tail_even(self):
        for address in (0,2,14,4094,4096,8190):
            for length in (18,22,34,110,144,176,210,292,2336):
                self.assertTrue(all(not(a%2 or b%2 or c%2) for a,b,c in p.compact_range(address,length)))

    def test_odd_base_and_odd_length_are_counterexamples(self):
        self.assertTrue(any(take%2 for _,_,take in p.compact_range(1,34)))
        self.assertTrue(any(take%2 for _,_,take in p.compact_range(2,33)))

    def test_all_weight_profiles_preserve_payload_parity(self):
        for profile,size in enumerate(p.mapping.SIZES,1):
            for offset in range(size):
                _,destination=p.mapping.weight_location(profile,offset)
                self.assertEqual(offset%2,destination%2)

    def test_activation_quant_mixed_layout_counterexample(self):
        # M8 context0 quant byte1 is source40, writer0 at even start40.
        ctx,off=p.mapping.activation_target(40,8,4,256)
        self.assertEqual((ctx,off),(0,5))
        plane,dest=p.mapping.activation_location(off,4,256)
        self.assertEqual((plane,dest),(0,1))
        self.assertNotEqual(40%2,dest%2)

    def test_even_domain_removes_weight_wrong_parity_only(self):
        possible,_=p.even_possible(0)
        weights=[key for key in possible if key[0]=='weight']
        self.assertTrue(weights)
        self.assertTrue(all(key[3]%2==key[4]%2 for key in weights))
        self.assertIn(('activation',0,0,1,0),possible)

    def test_pending_retains_writer_not_new_compact_index(self):
        key,slot,_=p.mapping.identity('gen_write_merge[0].gen_bank_plane[0].gen_bank_row[1].gen_byte_merge[5].hit',7)
        self.assertEqual((slot,key[-1]),(0,7))

    def test_fully_observed_or_single_direction_counterexample_rejected(self):
        for records in ({},{('x.hit',0):{'missing_serialized_coordinates':[1]}}):
            with self.assertRaises(ValueError): p.require_zero_bit(records,'x.hit',0)
        p.require_zero_bit({('x.hit',0):{'missing_serialized_coordinates':[0,1]}},'x.hit',0)


if __name__ == '__main__': unittest.main()
