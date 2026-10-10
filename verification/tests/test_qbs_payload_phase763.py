import sys
import unittest

import build_qbs_payload_phase763 as p
sys.path.insert(0,str(p.ROOT/'verification/coverage'))
import qualify_gap113_payload_full8 as independent


class PhaseTests(unittest.TestCase):
    def test_exact_novel_coordinates_and_ordered_truth(self):
        r=p.prediction()
        self.assertEqual((r['physical_bits'],r['raw_directions']),(144,288))
        self.assertTrue(all('bank1.' in t['scope'] and t['expected_hit_values']==[0,1,0] for t in r['targets']))

    def test_independent_native_unpack_complete_gold(self):
        for phase in (0,1):
            w,a,gold=p.fixture(phase)
            actual=independent.unpack(w[64+12*phase:944+12*phase],a[64+p.ASK[phase]:64+p.ASK[phase]+2336])
            self.assertEqual(actual['result_bits'],gold)
            self.assertEqual(actual['fflags'],0)
            self.assertEqual(len(gold),64)

    def test_host_guard_is_exact_new_phase_not_removed(self):
        body,_,_=p.templates()
        self.assertIn('c->activation_skew == (current == 0 ? 12u : 0u)',body)
        self.assertNotIn('c->activation_skew == 4',body)
        self.assertIn('c->weight_skew == (current == 0 ? 0u : 12u)',body)

    def test_guards_and_parity_remain_valid(self):
        for phase in (0,1):
            _,a,_=p.fixture(phase)
            start=64+p.ASK[phase]
            self.assertEqual(a[:start],bytes([0x5a])*start)
            self.assertEqual(a[start+2336:],bytes([0x5a])*(2496-start-2336))
            self.assertEqual(start%4,0)


if __name__=='__main__':unittest.main()
