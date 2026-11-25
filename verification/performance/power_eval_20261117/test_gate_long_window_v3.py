import unittest
import gate_long_window_v3 as g


class Windows(unittest.TestCase):
    def test_formal_spans(self):
        for key in ('q8', 'm1', 'm4'):
            c = g.CASES[key]
            self.assertGreaterEqual(c['last']-c['first'], 20000)
            g.limits('capture', c['first'], c['last'], c['maximum'], 14400, 48*1024**3, 14400)
        self.assertEqual(g.CASES['q8']['last']-g.CASES['q8']['first'], 43033)

    def test_akv_not_silently_admitted(self):
        c = g.CASES['akv_diag']
        self.assertTrue(c['diagnostic'])
        self.assertEqual(c['anchors']['formal_pending_cycles'], 41411)

    def test_limits_fail_closed(self):
        for first, last, maximum, size in ((0, 30000, 40000, 1024),
                (1000, 50000, 40000, 1024), (1, 30000, 40000, 65*1024**3)):
            with self.assertRaises(ValueError):
                g.limits('capture', first, last, maximum, 14400, size, 14400)

    def test_critical_x_vs_masked_data_warning(self):
        self.assertTrue(g.CRITICAL.search('input CLK unknown/high-Z'))
        self.assertTrue(g.CRITICAL.search('input CEB/CEBM unknown/high-Z'))
        self.assertFalse(g.CRITICAL.search('input D/DM unknown/high-Z'))


if __name__ == '__main__':
    unittest.main()
