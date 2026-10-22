import unittest
from unittest.mock import patch
import qualify_half_fma_routing_successor as q


class RoutingTests(unittest.TestCase):
    def test_all_coordinates(self):
        actual = q.coordinates()
        self.assertEqual(actual, {(lane, simd): lane+offset
            for lane in range(4) for simd, offset in enumerate((0, 8, 4, 12))})
        self.assertEqual(set(actual.values()), set(range(16)))

    def test_not_linear_simd(self):
        actual = q.coordinates()
        self.assertEqual(actual[0, 1], 8)
        self.assertNotEqual(actual[0, 1], 4)
        self.assertEqual(actual[3, 3]+16, 31)

    def test_mask_logical_not_physical(self):
        actual = q.coordinates()
        for (lane, _), index in actual.items():
            self.assertEqual(index % 2, lane % 2)

    def test_source_drift(self):
        with patch.object(q.life, 'digest', return_value='0'*64):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                q.coordinates()

    def test_scope_drift(self):
        with self.assertRaisesRegex(ValueError, 'Exact sixteen scopes'):
            q.wave(None, q.run.scopes()[:-1])

    def test_no_table_pattern_search(self):
        with patch.object(q.original.gold, 'PATTERNS', ()):
            self.assertEqual(q.coordinates()[2, 2], 6)


if __name__ == '__main__':
    unittest.main()
