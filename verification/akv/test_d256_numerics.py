import unittest

from analyze_d256_numerics import compute, error_summary, f16


class ScheduleTest(unittest.TestCase):
    def test_constant_scores_preserve_sum(self):
        for tile in (1, 64):
            output, changes = compute([0.0] * 4, [1.0, 2.0, 3.0, 4.0], 1, tile, True)
            self.assertEqual(output, [2.5])
            self.assertEqual(changes, [0])

    def test_half_rounding_is_not_final_only(self):
        scores, values = [0.0] * 4, [1024.0, f16(0.1), f16(0.1), f16(0.1)]
        half, _ = compute(scores, values, 1, 64, True)
        full, _ = compute(scores, values, 1, 64, False)
        self.assertEqual(half, [256.0])
        self.assertGreater(full[0], half[0])

    def test_error_boundary(self):
        result = error_summary([1.0, 1.2], [1.0, 1.0], 0.01, 0.01)
        self.assertEqual(result["mismatches"], 1)
        self.assertEqual(result["failed_indices"], [1])


if __name__ == "__main__":
    unittest.main()
