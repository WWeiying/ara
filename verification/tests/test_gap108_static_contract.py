import unittest
import gap108_static_contract as s


class Static(unittest.TestCase):
    def test_formal729_exact_seven_zero_coordinates(self):
        record=s.contract()
        self.assertEqual(len(record['targets']),7)
        self.assertEqual({(t['scope'],t['point']['raw_index']) for t in record['targets']},
                         {(scope,raw) for scope,indices in s.TARGETS.items() for raw in indices})
        self.assertTrue(all(t['before_hit'] is False and t['measured_hit'] is None
                            for t in record['targets']))
        self.assertFalse(record['coverage_admitted'])

    def test_independent_rounding_source_historical_pin_present(self):
        record=s.contract()
        p=str(s.ROOT/'hardware/deps/fpnew/src/fpnew_rounding.sv')
        self.assertEqual(record['pins'][p],
                         'b7ca1dcbe08ccd4eb0da15c4d514f1c23cc35be98d0363e832d518ebf4b3c543')


if __name__=='__main__':unittest.main()
