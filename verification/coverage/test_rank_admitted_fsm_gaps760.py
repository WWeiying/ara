import copy
import unittest
from unittest.mock import patch
import rank_admitted_fsm_gaps760 as rank


class Formal760Tests(unittest.TestCase):
    def test_exact_population_without_score_or_new_exclusion(self):
        result = rank.collect()
        self.assertEqual(result['population'], 760)
        self.assertEqual(result['qualified_exclusion_identities'], 155)
        self.assertFalse(result['official_percentages_recomputed'])
        self.assertFalse(result['exclusions_applied'])
        self.assertTrue(result['instances'])

    def reject_modified_bitmap(self, modify):
        read = rank.original.life.read_bound

        def altered(path, seal):
            value = read(path, seal)
            if path == rank.BASE / 'combined-bits.json':
                value = copy.deepcopy(value)
                modify(value)
            return value

        with patch.object(rank.original.life, 'read_bound', side_effect=altered):
            with self.assertRaises(ValueError):
                rank.collect()

    def test_duplicate_test_rejected(self):
        self.reject_modified_bitmap(lambda b: b['tests'].__setitem__(1, b['tests'][0]))

    def test_shape_drift_rejected(self):
        self.reject_modified_bitmap(lambda b: b['design'].__setitem__(
            'shape/fsm.verilog.shape.xml', '0' * 64))


if __name__ == '__main__':
    unittest.main()
