#!/usr/bin/env python3
"""Independent firmware oracle and fail-closed SoC collector tests."""
import unittest
from build_shared_alu_shift_mixed import evaluate
from run_shared_alu_shift_soc import parse
from test_shared_alu_soc import passing_log


class ShiftOracle(unittest.TestCase):
    def test_signed_rounding(self):
        for bits in range(256):
            signed = bits-256 if bits >= 128 else bits
            for shift in range(8):
                floor, remainder = divmod(signed, 1 << shift)
                half = (1 << shift)/2
                want = [floor+int(remainder >= half),
                        floor+int(remainder > half or (remainder == half and floor%2)),
                        floor, floor+int(remainder != 0 and not floor%2)]
                for mode in range(4):
                    self.assertEqual(evaluate('vssra', bits, shift, 8, mode), (want[mode]&255, False))

    def test_clip_boundaries(self):
        for width in (8,16,32):
            sw = 2*width; mask = (1 << width)-1
            for value in (-(1 << (width-1))-1, -(1 << (width-1)), -1, 0,
                          (1 << (width-1))-1, 1 << (width-1)):
                low = -(1 << (width-1)); high = (1 << (width-1))-1
                self.assertEqual(evaluate('vnclip', value & ((1 << sw)-1), 0, width, 1),
                                 (min(high,max(low,value)) & mask, value < low or value > high))
            self.assertEqual(evaluate('vnclipu', mask+1, 0, width, 0), (mask, True))

    def test_shift_count_masking(self):
        for op in ('vsll','vsrl','vsra','vnsrl','vnsra'):
            width = 16; sw = width * (2 if op.startswith('vn') else 1)
            for amount in range(sw):
                self.assertEqual(evaluate(op,0xfffeffff,amount,width,0),
                                 evaluate(op,0xfffeffff,amount+sw,width,0))


class ShiftCollector(unittest.TestCase):
    def test_requires_shift_timer(self):
        with self.assertRaises(ValueError): parse(passing_log(),'shift_mixed')
        self.assertEqual(parse(passing_log()+'\n[hw-cycles]: 50','shift_mixed')['hw_cycles'],['50'])

    def test_positive_timer(self):
        with self.assertRaises(ValueError): parse(passing_log()+'\n[hw-cycles]: 0','shift_mixed')

    def test_monitor_identity(self):
        text = passing_log().replace('ALU_SOC_MONITOR ara_tb.lane0.monitor',
                                     'ALU_SOC_MONITOR ara_tb.other.monitor')
        with self.assertRaises(ValueError): parse(text,'vadd')

    def test_dotproduct_regions(self):
        regions = [(s,n) for s in (8,16,32,64) for n in (8,64)] + [(8,512)]
        text = passing_log()+'\nSUCCESS.\n'+'\n'.join(
            f'Calulating {s}b dotp with vectors with length = {n}\nVector runtime: 10\nScalar runtime: 20'
            for s,n in regions)
        self.assertEqual(len(parse(text,'dotproduct')['dotproduct_regions']),9)
        with self.assertRaises(ValueError): parse(text.replace('length = 512','length = 64'),'dotproduct')

    def test_reject_failure_even_with_success(self):
        with self.assertRaises(ValueError): parse(passing_log()+'\nFatal: mismatch','vadd')

    def test_observation_checker_required(self):
        with self.assertRaises(ValueError): parse(passing_log(),'vadd',observation_aware=True)
        text = passing_log()+'\n'+'\n'.join(
            f'ALU_OBSERVATION_SUMMARY ara_tb.lane{lane}.monitor inactive_x_events=0' for lane in range(4))
        parse(text,'vadd',observation_aware=True)
        with self.assertRaises(ValueError):
            parse(text.replace('ALU_OBSERVATION_SUMMARY ara_tb.lane3',
                               'ALU_OBSERVATION_SUMMARY ara_tb.lane2'),'vadd',observation_aware=True)


if __name__ == '__main__':
    unittest.main()
