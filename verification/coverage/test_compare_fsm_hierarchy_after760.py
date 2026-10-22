import copy
import unittest

import compare_fsm_hierarchy_after760 as tool


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        def bitmap(n, bits):
            return dict(tests=['case%d' % i for i in range(n)], design={'shape': 'sealed'},
                        metrics={'fsm': {'scope': dict(width=3, checksum='123', bits=bits)}})
        self.a, self.b, self.c = bitmap(746, '4'), bitmap(760, '6'), bitmap(761, '7')
        self.p = dict(status='FORMAL760_FSM_PRIORITY_DIAGNOSTIC_ONLY',
            qualified_exclusion_identities=155, instances=[dict(scope='scope', checksum='123',
                missing=[dict(raw_position=2, kind='Transition', machine='state_q', name='A->B',
                              source_line='12', already_native_qualified_exclusion=False)])])

    def run_compare(self):
        return tool.compare(self.p, self.a, self.b, self.c)

    def test_new_hit_not_old_hit(self):
        row = self.run_compare()['instances'][0]
        self.assertEqual(row['points'][0]['classification'], 'NEW_RAW_HIT_AFTER760')
        self.assertEqual(row['already_hit746_positions'], [0])
        self.assertEqual(row['new_hit746_to760_positions'], [1])

    def test_qualified_missing_is_not_stimulus(self):
        self.c['metrics']['fsm']['scope']['bits'] = '6'
        self.p['instances'][0]['missing'][0]['already_native_qualified_exclusion'] = True
        self.assertEqual(self.run_compare()['instances'][0]['points'][0]['classification'],
                         'STILL_RAW_MISSING_NATIVE_QUALIFIED')

    def test_reject_changed_shape_and_lost_hit(self):
        for key, value in [('checksum', '999'), ('bits', '1'), ('bits', 'f')]:
            with self.subTest(key=key, value=value):
                saved = copy.deepcopy(self.c)
                self.c['metrics']['fsm']['scope'][key] = value
                with self.assertRaises(ValueError):
                    self.run_compare()
                self.c = saved

    def test_reject_duplicate_or_reordered_prefix(self):
        self.c['tests'][0] = self.c['tests'][1]
        with self.assertRaises(ValueError):
            self.run_compare()

    def test_reject_incomplete_or_wrong_position(self):
        self.p['instances'][0]['missing'][0]['raw_position'] = 0
        with self.assertRaises(ValueError):
            self.run_compare()


if __name__ == '__main__':
    unittest.main()
