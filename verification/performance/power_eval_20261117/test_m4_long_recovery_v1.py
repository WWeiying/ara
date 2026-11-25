"""Host admission tests; fixtures are never measurement activity."""
import unittest
import m4_long_recovery_v1 as m


class RecoveryTests(unittest.TestCase):
    def plan(self):
        return dict(case_id=m.CASE,init_seed=0,environment_diagnostic=False,
                    clock_period_ns=1,mode='capture',first_cycle=121568,last_cycle=213045)

    def test_exact_duration(self):
        self.assertEqual(m.validate_window(self.plan()),91477)

    def test_short_rejected(self):
        p=self.plan();p['last_cycle']=p['first_cycle']+19999
        with self.assertRaises(ValueError):m.validate_window(p)

    def test_other_case_rejected(self):
        p=self.plan();p['case_id']='legacy_q8_qbs_sdk_v2_successor'
        with self.assertRaises(ValueError):m.validate_window(p)

    def test_diagnostic_rejected(self):
        p=self.plan();p['environment_diagnostic']=True
        with self.assertRaises(ValueError):m.validate_window(p)

    def test_other_init_rejected(self):
        p=self.plan();p['init_seed']=1
        with self.assertRaises(ValueError):m.validate_window(p)

    def test_unknown_payload_cannot_proceed(self):
        with self.assertRaisesRegex(ValueError,'Unknown measured payload'):
            m.require_activity(dict(state='ACTIVITY_WINDOW_REJECTED',
                reasons=['Unknown measured payload while its operation is active']))

    def test_activity_eligible_is_not_task_pass(self):
        m.require_activity(dict(state='ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS',reasons=[]))


if __name__=='__main__':
    unittest.main()
