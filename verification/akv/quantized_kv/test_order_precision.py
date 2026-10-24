#!/usr/bin/env python3
"""Exact-double checks distinguish the actual first-product rounding points."""
import unittest

from analyze_rvv_order import block_precision,ulp_distance


class PrecisionTest(unittest.TestCase):
    def test_exact_small_integer_case(self):
        query=(b'\x00\x3c'+bytes([1])*32)*4
        for kind in (0,1):
            weights=(b'\x00\x3c'+bytes([0x99 if kind else 1])*(16 if kind else 32))*4
            rows=block_precision(kind,weights,query)
            self.assertEqual([r['integer_dot'] for r in rows],[32]*4)
            self.assertFalse(any(r['first_product_rounded'] or r['scale_product_rounded'] for r in rows))

    def test_large_q4_first_product_can_round(self):
        weights=b'\x55\xb5'+b'\x01'+bytes(15)+bytes(54)
        query=b'\x55\x35'+bytes([127])*32+bytes(102)
        row=block_precision(1,weights,query)[0]
        self.assertEqual(row['integer_dot'],-32385)
        self.assertTrue(row['first_product_rounded'])
        self.assertFalse(row['scale_product_rounded'])
        self.assertGreater(row['first_product_abs_rounding'],0)

    def test_ulp_order_including_negative_values(self):
        self.assertEqual(ulp_distance(0x3f800000,0x3f800001),1)
        self.assertEqual(ulp_distance(0xbf800000,0xbf800001),1)
        self.assertEqual(ulp_distance(0,0x80000000),1)


if __name__=='__main__':
    unittest.main()
