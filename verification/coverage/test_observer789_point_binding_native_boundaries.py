"""Native-header boundary fixtures only; no engine changes, disk writes or EDA."""
import unittest
import observer789_point_binding as owner
import test_observer788_readonly_counterexamples as fields
import test_observer788_readonly_branch_points as points


class NativeBoundaryNegatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ob, cls.old, _, _, _ = fields.fixtures()
        points.BranchPointCounterexample.setUpClass()
        cls.full = points.BranchPointCounterexample.full

    def reject(self, scope, module_crc, metric_crc, directive):
        extra = 'CHECKSUM: "%s %s"\nINSTANCE: %s\n%s\n' % (
            module_crc,metric_crc,scope,directive)
        with self.assertRaises(ValueError): owner.native_gate(self.full+extra,self.old,self.ob)

    def test_foreign_module_crc_with_actual_branch_crc(self):
        self.reject(owner.SCOPES[0],'2332976183','2887169998','Branch 0')

    def test_toggle_crc_not_a_branch_crc(self):
        self.reject(owner.SCOPES[0],'2332976182','498965595','Branch 0')

    def test_line_crc_not_a_branch_crc(self):
        self.reject(owner.SCOPES[0],'2332976182','1382966637','Branch 0')

    def test_compiled_zero_child_cannot_gain_branch_directive(self):
        self.assertEqual(self.ob['capacities'][owner.SCOPES[1]]['branch'],0)
        self.reject(owner.SCOPES[1],'1958759582','2981092130','Branch 0')

    def test_compiled_zero_condition_and_fsm_cannot_gain_directives(self):
        for directive in ('Condition 0','Fsm 0'):
            self.reject(owner.SCOPES[0],'2332976182','498965595',directive)

    def test_foreign_branch_vector_and_signature_fail_closed(self):
        expression = owner.binding()['branch_schema']['0']['expressions'][0]['exprstr']
        for vector in ('0','999999'):
            directive = 'Branch 0 "3741044968" "%s" (%s) "unobserved-signature"' % (expression,vector)
            self.reject(owner.SCOPES[0],'2332976182','2887169998',directive)

    def test_typed_positive_control_still_valid(self):
        owner.native_gate(self.full,self.old,self.ob)


if __name__ == '__main__': unittest.main()
