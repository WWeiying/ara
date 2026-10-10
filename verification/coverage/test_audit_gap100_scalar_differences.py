import unittest
from types import SimpleNamespace

import audit_gap100_scalar_differences as m


class DifferenceTests(unittest.TestCase):
    def commit(self, **changes):
        fields = dict(pc=0x80002000, instruction=0x13, gpr_writes={}, memory_accesses=(),
                      vector_writes={}, fpr_writes={})
        fields.update(changes)
        return SimpleNamespace(**fields)

    def test_shape_mismatch_never_normalized(self):
        for rhs in ([], [self.commit(pc=0x80002004)], [self.commit(instruction=0x93)]):
            with self.assertRaises(ValueError):
                m.differences([self.commit()], rhs)

    def test_bit7_candidate_not_approval(self):
        result = m.differences([self.commit(gpr_writes={11: 128})], [self.commit(gpr_writes={11: 0})])
        self.assertTrue(result[0]['bit7_only_value_difference'])
        result = m.differences([self.commit(gpr_writes={11: 129})], [self.commit(gpr_writes={11: 0})])
        self.assertFalse(result[0]['bit7_only_value_difference'])

    def test_address_difference_not_bit7(self):
        result = m.differences([self.commit(memory_accesses=((0x80003000, 128),))],
                               [self.commit(memory_accesses=((0x80003008, 0),))])
        self.assertFalse(result[0]['bit7_only_value_difference'])


if __name__ == '__main__':
    unittest.main()
