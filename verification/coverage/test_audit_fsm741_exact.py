import unittest
import audit_fsm741_exact as a


class NativeTest(unittest.TestCase):
    text = 'CHECKSUM: "1251950563 3476102610"\nINSTANCE: exact.scope\nFsm state_q "3476102610"\nANNOTATION: "proof"\nState KILL_MISS "4"\n'

    def test_real_singleton_grammar(self):
        self.assertEqual(a.native_records(self.text)[0][-3:], ('State', 'KILL_MISS', '4'))

    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            a.native_records(self.text + 'State KILL_MISS "4"\n')

    def test_unknown_attribute_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            a.native_records(self.text + 'Default all\n')

    def test_missing_annotation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            a.native_records(self.text.replace('ANNOTATION: "proof"\n', ''))

    def test_state_inheritance_recorded_but_protected_transition_strict(self):
        p = dict(strategy='direct-transition-only-66', groups=[dict(scope='s', machine=dict(name='m'),
            mode='State', rows=[dict(name='IDLE', target=False)]), dict(scope='s', machine=dict(name='m'),
            mode='Transition', rows=[dict(name='A->B', target=False)])])
        rows = []
        for stage in ('initial', 'applied', 'reset', 'reloaded', 'final'):
            inherit = stage in ('applied', 'reloaded')
            rows += [[stage, 's', 'm', 'State', 'IDLE', '1' if inherit else '0',
                      'INHERITED_OBSERVATION' if inherit else '0'],
                     [stage, 's', 'm', 'Transition', 'A->B', '0', '0']]
        a.audit_points(rows, p)
        rows[3][5] = '1'
        with self.assertRaisesRegex(ValueError, 'state differs'):
            a.audit_points(rows, p)

    def test_reset_state_still_strict(self):
        p = dict(strategy='direct-transition-only-66', groups=[dict(scope='s', machine=dict(name='m'),
                 mode='State', rows=[dict(name='IDLE', target=False)])])
        with self.assertRaisesRegex(ValueError, 'state differs'):
            a.audit_points([['reset', 's', 'm', 'State', 'IDLE', '1', '0']], p)

    def test_native_target_authority_cannot_extend_to_protected_point(self):
        p = dict(strategy='direct-transition-only-66', point_query_authority='saved-native-identity',
                 groups=[dict(scope='s', machine=dict(name='m'), mode='Transition',
                              rows=[dict(name='A->B', target=True), dict(name='B->A', target=False)])])
        rows = []
        for stage in ('initial', 'applied', 'reset', 'reloaded', 'final'):
            rows += [[stage, 's', 'm', 'Transition', 'A->B', '0',
                      'NATIVE_EL_AUTHORITY' if stage in ('applied', 'reloaded') else '0'],
                     [stage, 's', 'm', 'Transition', 'B->A', '0', '0']]
        a.audit_points(rows, p)
        rows[3][-1] = 'NATIVE_EL_AUTHORITY'
        with self.assertRaisesRegex(ValueError, 'state differs'):
            a.audit_points(rows, p)


if __name__ == '__main__':
    unittest.main()
