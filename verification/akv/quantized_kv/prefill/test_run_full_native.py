import unittest
from run_full_native import require_full_build


class BuildGateTest(unittest.TestCase):
    def test_whole_call_build(self):
        report = dict(whole_call=True, rebuilt_objects=15, reused_objects=0,
                      commands_per_trial=4, outputs_per_trial=1024,
                      value_decodes=[74, 20, 20, 74], state='BUILT_NOT_EXECUTED')
        require_full_build(report)
        for key, wrong in [('whole_call', False), ('whole_call', 1),
                           ('rebuilt_objects', 13), ('reused_objects', 1),
                           ('commands_per_trial', 0), ('outputs_per_trial', 0),
                           ('value_decodes', [74, 74, 74, 74]), ('state', 'PASS')]:
            with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError):
                require_full_build(dict(report, **{key: wrong}))
        for key in report:
            missing = dict(report)
            del missing[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                require_full_build(missing)


if __name__ == '__main__':
    unittest.main()
