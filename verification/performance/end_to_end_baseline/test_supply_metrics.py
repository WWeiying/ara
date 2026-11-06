"""Decision metrics are independent of the functional acceptance status."""
from copy import deepcopy
import unittest

import check_supply_sdk as c
from test_supply_decode import stream
from test_supply_sdk import full_stream


class SupplyMetricsTests(unittest.TestCase):
    def test_asymmetric_region_ratios_and_decision_boundaries(self):
        for kind in ('decode', 'prefill'):
            if kind == 'decode': text, *oracle = stream(128)
            else: text, oracle = full_stream(128)
            base = c.check(text, kind, 128, oracle)
            def region(value):
                return value['total'] if kind == 'decode' else value['trials'][0]
            region(base)['region'] = 1000
            for cycles, sufficient, regression in ((900, True, False), (901, False, False),
                                                  (1020, False, False), (1021, False, True)):
                candidate = deepcopy(base); region(candidate)['region'] = cycles
                result = c.paired(base, candidate, kind)
                with self.subTest(kind=kind, cycles=cycles):
                    self.assertAlmostEqual(result['speedups']['region'], 1000/cycles)
                    self.assertEqual(result['region_cycles_reduced_at_least_10_percent'], sufficient)
                    self.assertEqual(result['region_regression_above_2_percent'], regression)

    def test_changed_payload_is_not_a_speedup(self):
        text, *oracle = stream(128); base = c.check(text, 'decode', 128, oracle)
        candidate = deepcopy(base); candidate['activity'][0]['counters']['weight_bytes'] -= 1
        with self.assertRaisesRegex(ValueError, 'Unequal physical payload'):
            c.paired(base, candidate, 'decode')


if __name__ == '__main__': unittest.main()
