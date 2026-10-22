import copy
import unittest
from unittest.mock import patch
import gap110_q3_r4_contract as s


class NativeTests(unittest.TestCase):
    def test_both_native_oracles(self):
        for phase,n in ((0,7),(1,5)):
            w,a=s.fixtures(phase);r=s.unpack_oracle(w,a,n)
            self.assertEqual(len(r['bits']),5*n)
            self.assertEqual(r['flags'],0)
            self.assertEqual(r['bits'],[0x43800000]*n+[0x44000000]*n+[0x44400000]*n+[0x44800000]*n+[0x44a00000]*n)

    def test_bad_bsum_rejected(self):
        w,a=s.fixtures(0);a=bytearray(a);a[2080]^=1
        with self.assertRaises(ValueError):s.unpack_oracle(w,a,7)

    def test_changed_quant_not_hidden(self):
        w,a=s.fixtures(0);w=bytearray(w);w[32]^=1
        self.assertNotEqual(s.unpack_oracle(w,a,7)['bits'][0],0x43800000)

    def test_changed_scale_not_hidden(self):
        w,a=s.fixtures(0);w=bytearray(w);w[96]^=1
        self.assertNotEqual(s.unpack_oracle(w,a,7)['bits'][0],0x43800000)

    def test_wrong_size_profile_scale_rejected(self):
        w,a=s.fixtures(0)
        with self.assertRaises(ValueError):s.unpack_oracle(w[:-1],a,7)
        w=bytearray(w);w[108]^=1
        with self.assertRaises(ValueError):s.unpack_oracle(w,a,7)

    def test_two_phases_only(self):
        for phase in (True,2,-1):
            with self.assertRaises(ValueError):s.fixtures(phase)


class CompiledTests(unittest.TestCase):
    def test_real_26_targets(self):
        result=s.contract()
        self.assertEqual(len(result['targets']),26)
        self.assertEqual([t['point']['raw_index'] for t in result['targets']],
            [11128+8*i for i in range(14)]+[10348+8*i for i in range(12)])
        self.assertEqual(len({(t['scope'],t['point']['raw_index']) for t in result['targets']}),26)
        self.assertTrue(all(t['before_hit'] is False and t['measured_hit'] is None for t in result['targets']))

    def test_already_hit_rejected(self):
        with patch.object(s.mapping,'bit',return_value=True):
            with self.assertRaises(ValueError):s.contract()

    def test_compiled_identity_drift_rejected(self):
        original=s.mapping.inventory.points
        def altered(*args):
            points=copy.deepcopy(original(*args));points[11128]['native_id']='0';return points
        with patch.object(s.mapping.inventory,'points',side_effect=altered):
            with self.assertRaises(ValueError):s.contract()

    def test_source_pin_drift_rejected(self):
        with patch.object(s.life,'check',side_effect=ValueError('source drift')):
            with self.assertRaises(ValueError):s.contract()


if __name__=='__main__':unittest.main()
