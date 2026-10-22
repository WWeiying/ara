import unittest
import preflight_mask_compare_restart785 as p


class GoldTests(unittest.TestCase):
    def test_independent_active_and_prestart(self):
        for start in p.STARTS:
            value=int.from_bytes(p.mask_gold(start),'little')
            for i in range(64):
                self.assertEqual(bool(value>>i&1),i>=start and (17*i+5)%256<(29*i+3)%256)

    def test_whole_source(self):
        self.assertEqual(len(p.source_bytes(0)),128)
        self.assertEqual(len(p.source_bytes(1)),128)
        self.assertNotEqual(p.source_bytes(0),p.source_bytes(1))

    def test_illegal_start_rejected(self):
        with self.assertRaises(Exception): p.mask_gold(65)

    def test_no_tail_in_mask_export(self):
        self.assertTrue(all(len(p.mask_gold(s))==8 for s in p.STARTS))

    def test_implicit_vector_opcode_rejected(self):
        with self.assertRaises(Exception): p.linked('80002000: 02000007 vle8.v v0, (a0)\n')

    def test_actual_frozen_source_pins(self):
        q=p.life.read_bound(p.PLAN,p.PLAN_SHA)
        p.life.check(q['source_pins'])


if __name__=='__main__': unittest.main()
