#!/usr/bin/env python3
"""Fail-closed collector tests and independent rounding-model checks."""
import unittest
from build_shared_alu_mixed import average
from run_shared_alu_soc import parse, reference_module


def passing_log():
    lines = ['Core Test *** SUCCESS ***', '$finish at simulation time 100000']
    for lane in range(4):
        name = f'ara_tb.lane{lane}.monitor'
        lines += [f'ALU_SOC_MONITOR {name}',
            f'ALU_SOC_ACTIVITY {name} eval=1,2,3,4 wb=8 wb_blocked=0 pending=3 queue_full=0 mask=2']
    return '\n'.join(lines)


class Collector(unittest.TestCase):
    def test_named_module_end(self):
        source = 'module simd_alu; endmodule : simd_alu'
        self.assertEqual(reference_module(source),
                         'module simd_alu_reference; endmodule : simd_alu_reference')

    def test_pass(self):
        self.assertEqual(parse(passing_log(),'vadd')['finish_time'],'100000')

    def test_fatal_with_eoc_rejected(self):
        with self.assertRaises(ValueError):
            parse(passing_log()+'\nFatal: mismatch','vadd')

    def test_duplicate_lane_rejected(self):
        with self.assertRaises(ValueError):
            parse(passing_log().replace('lane3','lane2'),'vadd')

    def test_missing_check_rejected(self):
        with self.assertRaises(ValueError):
            parse(passing_log().replace('Core Test *** SUCCESS ***',''),'vadd')

    def test_no_activity_rejected(self):
        with self.assertRaises(ValueError):
            parse(passing_log().replace('eval=1,2,3,4','eval=0,0,0,0'),'vadd')

    def test_missing_app_regions_rejected(self):
        for case in ('mixed','dotproduct','llama_q4km_micro'):
            with self.assertRaises(ValueError):
                parse(passing_log(),case)

    def test_signed_average_exhaustive_ew8(self):
        # Independent oracle: divide the exact signed sum, choose the rounded
        # integer by ties/oddness, and only then truncate to the output width.
        for a in range(-128,128):
            for b in range(-128,128):
                total = a+b; floor,remainder = divmod(total,2)
                want = [floor+remainder,
                        floor+int(bool(remainder) and floor%2 != 0),
                        floor, floor+int(bool(remainder) and floor%2 == 0)]
                for mode in range(4):
                    self.assertEqual(average(a&255,b&255,8,mode),want[mode]&255)


if __name__ == '__main__':
    unittest.main()
