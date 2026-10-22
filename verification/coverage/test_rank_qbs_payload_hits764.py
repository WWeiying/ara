import unittest
import rank_qbs_payload_hits764 as r


class TestMapping(unittest.TestCase):
    def test_enum_not_logical_format_index(self):
        self.assertEqual(r.FORMATS[2],'Q6_K');self.assertEqual(r.ENUMS[2],2)
        self.assertEqual(r.FORMATS[3],'Q3_K');self.assertEqual(r.ENUMS[3],5)
    def test_second_weight_bank_uses_global_row4_base(self):
        # Q3 size110: bank1 base shift4*110 =8 mod16, not bank0 phase.
        self.assertEqual(len(next(iter(r.weight_beats(4,0,True,0)))),16)
        self.assertEqual(len(next(iter(r.weight_beats(4,0,True,1)))),8)
    def test_all_weight_bytes_once_and_all_phases_even(self):
        for profile in range(1,10):
            for phase in range(0,16,2):
                for grouped in (False,True):
                    beats=list(r.weight_beats(profile,phase,grouped))
                    self.assertEqual(sum(map(len,beats)),4*r.proof.mapping.SIZES[profile-1])
                    for beat in beats:self.assertEqual([t[-1] for t in beat],list(range(len(beat))))
    def test_bank1_rowmajor_not_legally_addressable(self):
        keys=r.trace_keys(r.activation_beats(4,256,1,0),1)
        self.assertEqual(keys,(set(),set(),set()))
    def test_M8_banks_both_and_context_parity_not_dest_parity(self):
        beats=list(r.activation_beats(4,256,8,0))
        for bank in (0,1):
            side,newer,pending=r.trace_keys(beats,bank)
            self.assertTrue(side);self.assertTrue(newer)
        self.assertTrue(any(t[0]=='activation' and t[1]==0 and t[2]==0 and t[3]==1 and t[4]==0
            for beat in r.activation_beats(4,256,8,8) for t in beat))
    def test_pending_not_assumed_all_mask_bits(self):
        side,newer,pending=r.trace_keys([[('weight',0,0,0,0),('weight',0,0,16,1)]],0)
        self.assertIn(('weight',0,0,0,0),newer)
        self.assertIn(('weight',0,0,0,1),pending)
        self.assertNotIn(('weight',0,0,0,0),pending)


if __name__=='__main__':unittest.main()
