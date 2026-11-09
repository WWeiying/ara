#!/usr/bin/env python3
"""Host contract tests only; no claim of QK RTL execution or acceptance."""
from collections import Counter
import unittest

from geometry import control, fpnew_sample, layout, private_mask, scalar_locations


class QKGeometry(unittest.TestCase):
    def test_all_bounded_output_locations_and_bytes(self):
        for t in range(1, 65):
            for h in (1, 2):
                for vd in (0, 16, 28):
                    with self.subTest(tokens=t, heads=h, vd=vd):
                        positions = scalar_locations(t, h, vd)
                        self.assertEqual(Counter(positions.values()),
                                         Counter((head, token) for head in range(h) for token in range(t)))
                        masks = layout(t, h, vd)
                        self.assertEqual(sum(bin(w['byte_enable']).count('1')
                                             for l in masks for w in l['writes']), t*h*4)
                        self.assertTrue(all(4*vd <= w['address'] < 4*vd+16 and w['slot'] < 16
                                            for l in masks for w in l['writes']))

    def test_shared_accumulator_capacity(self):
        for t in range(1, 65):
            for h in (1, 2):
                for lane in layout(t, h):
                    self.assertLessEqual(len(lane['writes']), 16)
        self.assertEqual([len(l['writes']) for l in layout(64, 2)], [16]*4)
        self.assertEqual([len(l['writes']) for l in layout(9, 2)], [4, 2, 2, 2])

    def test_t1_inactive_lanes_and_tail(self):
        lanes = layout(1, 1)
        self.assertEqual([l['active'] for l in lanes], [True, False, False, False])
        self.assertEqual(lanes[0]['writes'][0]['byte_enable'], 0x0f)
        self.assertTrue(all(not l['writes'] for l in lanes[1:]))

    def test_fpnew_stride_for_both_formats(self):
        for elements in (2, 4):
            for fp_lanes in (4, 8):
                for mask in range(1 << elements):
                    self.assertEqual(fpnew_sample(private_mask(mask, elements, fp_lanes),
                                                  elements, fp_lanes), mask)
        self.assertEqual(private_mask(3, 2, 4), 15)
        self.assertEqual(private_mask(1, 2, 4), 3)
        self.assertNotEqual(fpnew_sample(3, 2, 4), 3)

    def test_q_selection_and_control_round_trip(self):
        for rows in range(1, 9):
            for base in range(rows):
                for h in (1, 2):
                    if base+h > rows:
                        with self.assertRaises(ValueError): control(64, h, 128, base, rows)
                        continue
                    for d, code in ((64, 0), (128, 1), (96, 2)):
                        value = control(64, h, d, base, rows)
                        self.assertEqual((value & 63, (value >> 6) & 1,
                                          (value >> 7) & 3, value >> 9), (63, h-1, code, base))

    def test_reject_bad_geometry(self):
        for args in ((0, 1), (65, 2), (9, 0), (9, 3), (9, 2, 2), (9, 2, 32)):
            with self.assertRaises(ValueError): layout(*args)
        for args in ((0, 1, 128), (1, 1, 256), (1, 2, 64, 7), (1, 1, 64, 0, 0)):
            with self.assertRaises(ValueError): control(*args)


if __name__ == '__main__': unittest.main()
