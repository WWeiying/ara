import copy
import unittest
from audit import audit


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(cases=[dict(name='one', sha256='abc',
                                        pass_marker='RVV_PASS')], archive_sha256='xyz')
        self.report = dict(inputs=copy.deepcopy(self.manifest), rtl_modified=False,
                           board_reset=False, state='all_cases_finished_review_results',
                           results=[dict(name='one', status='passed', exit_code=0,
                                         output='RVV_PASS cases=21 errors=0\r\n')])

    def test_pass_count(self):
        result = audit(self.manifest, self.report)
        self.assertTrue(result['passed'])
        self.assertEqual(result['passing_configurations'], 21)

    def test_echo_is_not_pass(self):
        self.report['results'][0]['output'] = 'printf RVV_PASS cases=21'
        with self.assertRaises(ValueError):
            audit(self.manifest, self.report)

    def test_numerical_failure_does_not_mean_incomplete(self):
        self.report['results'][0].update(status='failed', exit_code=1)
        result = audit(self.manifest, self.report)
        self.assertTrue(result['complete'])
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['findings']), 1)

    def test_running_is_not_complete(self):
        self.report['results'][0]['status'] = 'running'
        with self.assertRaises(ValueError):
            audit(self.manifest, self.report)

    def test_changed_identity_is_rejected(self):
        self.report['inputs']['cases'][0]['sha256'] = 'different'
        with self.assertRaises(ValueError):
            audit(self.manifest, self.report)


if __name__ == '__main__':
    unittest.main()
