import unittest

from run_wide_complete_engine import BASE
from balanced_engine_fixture import bench, wrapper


class EngineFixture(unittest.TestCase):
    def test_only_internal_route_and_probes_change(self):
        source=(BASE/'tree/matrix_fault_suite.sv').read_text()
        wrap=(BASE/'tree/matrix_wrapper.sv').read_text()
        for clone in (0,1):
            text,report=bench(source,clone);w,r=wrapper(wrap,clone)
            for guard in ('dot_active_cycles != expected_dot_cycles','expected_low',
                          'QBS context weight fault/retry PASS','QBS next-block reset/replay PASS',
                          'QBS MMU atomic-fault PASS','Full controller selected wrong transfer size',
                          'memory_byte(response_bus_addr + byte_lane)',
                          'phase_fault_cycles + phase_terminal_cycles !='):
                self.assertTrue(guard in text,guard)
            self.assertIn('parameter bit Balanced = 0',text)
            self.assertEqual(text.count('BE_WORK case='),1)
            self.assertEqual(text.count('BE_PHASE case='),1)
            self.assertIn('BE_CONFIG clone='+str(clone),text)
            self.assertIn('.PerRangeTransferSize(WideWeight)',w)
            self.assertEqual('qbs_engine_balanced #(' in w,bool(clone))
            self.assertEqual("+ int'(`FP_PROBE.mixed_fire)" in text,bool(clone))
            self.assertEqual('!`FP_PROBE.mixed_found' in text,bool(clone))
            self.assertTrue(report['golden_fault_and_context_checks_retained'])

    def test_missing_or_duplicate_anchor_fails(self):
        for fn,name in ((bench,'matrix_fault_suite.sv'),(wrapper,'matrix_wrapper.sv')):
            source=(BASE/'tree'/name).read_text()
            for bad in ('',source+source):
                with self.assertRaises(ValueError):fn(bad,1)


if __name__=='__main__':unittest.main()
