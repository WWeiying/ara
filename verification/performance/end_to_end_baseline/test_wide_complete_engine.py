"""Host gates for the complete-controller wide-service successor fixture."""
import unittest

import run_wide_complete_engine as c


class CompleteEngineTests(unittest.TestCase):
    def setUp(self):
        self.bench = (c.BASE / 'tree/matrix_fault_suite.sv').read_text()
        self.wrapper = (c.BASE / 'tree/matrix_wrapper.sv').read_text()

    def test_successor_keeps_golden_and_atomic_checks(self):
        text = c.bench_source(self.bench)
        for needle in ('dot_active_cycles != expected_dot_cycles',
                       'expected_low', 'QBS next-block reset/replay PASS',
                       'QBS MMU atomic-fault PASS', 'QBS context weight fault/retry PASS',
                       'physical_range_allowed = 1\'b1;',
                       'response_size[response_wr] <= axi_ar.size;',
                       'memory_byte(response_bus_addr + byte_lane)',
                       'Full controller selected wrong transfer size'):
            self.assertIn(needle, text)
        self.assertNotIn('response_beat * BeatBytes + byte_lane', text)
        self.assertEqual(text.count('WIDE_ENGINE_TRAFFIC case='), 1)

    def test_wrapper_connects_only_matching_width_modes(self):
        text = c.wrapper_source(self.wrapper)
        self.assertIn('WideWeight = AxiDataWidth == 256', text)
        self.assertIn('.WideWeightIngress(WideWeight)', text)
        self.assertIn('.PerRangeTransferSize(WideWeight)', text)

    def test_anchor_drift_rejected(self):
        for text in ('', self.bench + self.bench):
            with self.assertRaises(ValueError): c.bench_source(text)
        with self.assertRaises(ValueError): c.wrapper_source('')

    def test_no_plain_baseline_or_fatal_accepted(self):
        log = (c.BASE / 'functional.log').read_text()
        vector = (c.ORIGINAL / 'matrix-base.txt').read_text()
        for text in (log, log + '\nFatal: unexpected\n'):
            with self.assertRaises(ValueError): c.check(text, vector, 128, 0)


if __name__ == '__main__':
    unittest.main()
