#!/usr/bin/env python3
"""Geometry, original-head mapping and bounds, without native acceptance claims."""
import unittest
from batch_spec import sequence, expected


class BatchGeometryTest(unittest.TestCase):
    def test_all_original_heads_and_tokens_once_before_tails(self):
        commands = sequence()
        self.assertEqual((expected()['commands'],expected()['outputs']),(40,3336))
        self.assertEqual({c.m for c in commands},{2,4})
        self.assertEqual({c.n for c in commands},{1,31,32})
        for kind in range(2):
            seen = []
            for c in commands:
                if c.kind != kind or c.n != 32:
                    continue
                seen += [(q,t) for q in range(c.first_q,c.first_q+c.m)
                         for t in range(c.first_token,c.first_token+c.n)]
            self.assertEqual(len(seen),len(set(seen)))
            self.assertEqual(set(seen),{(q,t) for q in range(12) for t in range(128)})

    def test_no_hidden_rows_or_cross_kv_heads(self):
        for c in sequence():
            self.assertTrue(c.kv_head*6 <= c.first_q < c.first_q+c.m <= (c.kv_head+1)*6)
            self.assertLessEqual(c.first_token+c.n,128)
            for column in range(c.n):
                start,end = c.key_range(column)
                self.assertEqual(end-start,c.weight_row_bytes)
                self.assertEqual(start % 2,0)
                self.assertLessEqual(end,(c.kv_head*256+128)*c.weight_row_bytes)
            with self.assertRaises(ValueError):
                c.key_range(c.n)


if __name__ == '__main__':
    unittest.main()
