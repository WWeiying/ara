import unittest
import preflight_qbs_route770_v2 as v


class KDomainTests(unittest.TestCase):
    def test_range_phase_not_descriptor_phase(self):
        c=v.p.configuration('Q4_0','ROW',0,0)
        shifted=dict(c,activation_phase=2)
        original={e for b in v.p.streams(c,'activation',0) for e in v.p.overapprox(b,'activation',1)}
        extra={e for b in v.p.streams(shifted,'activation',0) for e in v.p.overapprox(b,'activation',1)}
        self.assertTrue(extra-original)
        with self.assertRaises(ValueError):v.p.configuration('Q4_0','ROW',0,2)

    def test_all_k_residues(self):
        self.assertEqual({(34*k)%16 for k in range(256)},set(range(0,16,2)))
        self.assertEqual({(292*k)%16 for k in range(256)},{0,4,8,12})
        self.assertEqual({(8*34*k)%16 for k in range(256)},{0})

    def test_actual_full_partition(self):
        r=v.collect();self.assertEqual(sum(r['classification_counts'].values()),13428)
        self.assertFalse(r['simulation_recommended']);self.assertFalse(r['coverage_admitted'])


if __name__=='__main__':unittest.main()
