import unittest
import audit_operand_condition_scope_722 as subject


class ScopeTests(unittest.TestCase):
    def point(self, vector='1'):
        return dict(native_vector={'vector': vector},
                    expressions=[dict(exprstr='SupportIntExt2', index='1', id='339')])

    def test_exact_parameter_true_demand_only(self):
        label, proof = subject.branch_decision(self.point(), False, False, True)
        self.assertEqual(label, 'NEW_CONFIG_PROOF_NATIVE_HOLD')
        self.assertEqual(len(proof), 1)
        label, proof = subject.branch_decision(self.point('0'), False, False, True)
        self.assertEqual(label, 'PROTECTED_ZERO_NO_CONFIG_PROOF')
        self.assertFalse(proof)

    def test_already_policy_not_new(self):
        self.assertEqual(subject.branch_decision(self.point(), False, True, True)[0],
                         'PROVEN_GUARD_ALREADY_EXISTING_POLICY')

    def test_hit_contradiction_and_unbound_variants(self):
        with self.assertRaises(ValueError):
            subject.branch_decision(self.point(), True, False, True)
        self.assertEqual(subject.branch_decision(self.point(), False, False, False)[0],
                         'PROTECTED_ZERO_NO_CONFIG_PROOF')

    def test_condition_no_checksum_hold_and_conflict(self):
        self.assertEqual(subject.condition_binding(None, None), 'HOLD_NO_PER_INSTANCE_CHECKSUM')
        self.assertEqual(subject.condition_binding(None, '123'), 'COMPILED_ONLY_NOT_NATIVE')
        with self.assertRaises(ValueError):
            subject.condition_binding('456', '123')


if __name__ == '__main__':
    unittest.main()
