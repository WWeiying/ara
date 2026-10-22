import unittest
import preflight_qbs_route770 as p


class RoutingTests(unittest.TestCase):
    def test_compact_beats(self):
        self.assertEqual(list(p.beats(34,4)),[(0,12),(12,16),(28,6)])
        self.assertEqual(list(p.beats(18,2)),[(0,14),(14,4)])

    def test_negative_descriptor_alignment(self):
        with self.assertRaises(ValueError):p.configuration('Q5_K','M8',1,4)
        with self.assertRaises(ValueError):p.configuration('Q5_K','M8',2,2)
        with self.assertRaises(ValueError):p.configuration('invalid','M8',2,4)

    def test_m8_bank1_context(self):
        c=p.configuration('Q5_K','M8',2,4)
        self.assertEqual(p.activation_map(c,44,0),(4,5,True))
        self.assertEqual(p.activation_map(c,32,0),(0,4,True))

    def test_weight_parity_negative(self):
        for profile in p.PROFILES:
            c=p.configuration(profile,'M8',2,4)
            for beat in p.streams(c,'weight',0):
                for t in beat['targets']:
                    if t['valid'] and t['plane']<2:self.assertEqual(t['loc']%2,t['b']%2)

    def test_side_not_payload(self):
        c=p.configuration('Q5_K','M8',0,0);b=next(p.streams(c,'weight',0))
        events,rem=p.cycle(None,b,'weight')
        self.assertTrue(events);self.assertTrue(all(k[1][0]=='group_hit' for k in events));self.assertEqual(rem,[None,None])

    def test_pending_keeps_byte_index(self):
        c=p.configuration('Q5_K','M8',2,4)
        beat=list(p.streams(c,'weight',0))[2]
        _,rem=p.cycle(None,beat,'weight')
        if rem[1]:self.assertEqual([t['b'] for t in rem[1]['targets']],list(range(16)))
        events=p.trace(c,'weight',0);self.assertTrue(events)

    def test_bank1_rowmajor_protected(self):
        c=p.configuration('Q4_0','ROW',2,4)
        self.assertFalse(any(t['valid'] for b in p.streams(c,'activation',1) for t in b['targets']))


if __name__=='__main__':unittest.main()
