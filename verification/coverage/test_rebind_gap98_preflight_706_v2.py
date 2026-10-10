import unittest
import rebind_gap98_preflight_706_v2 as m


class RebindTests(unittest.TestCase):
    def scopes(self):
        return ["ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.gen_num_lanes[%d].x_ct_vfdsu_pack" % (l, s)
                for l in range(4) for s in (2, 3)]

    def test_all_eight(self):
        self.assertEqual(m.select_scopes(self.scopes()), self.scopes())

    def test_missing_slot3(self):
        with self.assertRaises(ValueError):
            m.select_scopes(self.scopes()[:-1])

    def test_ambiguous(self):
        with self.assertRaises(ValueError):
            m.select_scopes(self.scopes() + [self.scopes()[0]])

    def test_preserve(self):
        rows = [dict(scope=s, bitmap=i) for i, s in enumerate(self.scopes())]
        m.preserve_rows(rows[::2], rows)
        changed = [dict(r) for r in rows]
        changed[0]["bitmap"] = -1
        with self.assertRaises(ValueError):
            m.preserve_rows(rows[::2], changed)

    def test_duplicate_rows(self):
        rows = [dict(scope=s) for s in self.scopes()]
        with self.assertRaises(ValueError):
            m.preserve_rows(rows[::2], rows[:-1] + [rows[0]])


if __name__ == "__main__":
    unittest.main()
