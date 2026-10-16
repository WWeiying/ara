import copy
import unittest
from audit_permute_stall import validate_stall, TRIGGER


class StallTests(unittest.TestCase):
    def report(self):
        a = dict(identity=dict(frequency_hz=50), live=dict(run_id=1, flags=0),
                 watchdog_snapshot=False, core=dict(cycles=100, retired=5, trap_count=1, last_pc=8, head_pc=12))
        b = copy.deepcopy(a); b['core']['cycles'] = 300
        return dict(results=[dict(name='test', status='stalled', output=TRIGGER)],
                    progress_diagnosis=dict(name='test', stalled=True, snapshots=[a, b]))

    def test_live_stall(self):
        self.assertEqual(len(validate_stall(self.report(), 'test', True)), 2)

    def test_progress_and_stopped_snapshots_rejected(self):
        for section, key, value in (('core', 'retired', 6), ('core', 'cycles', 100),
                                    ('live', 'flags', 1), ('live', 'run_id', 2)):
            report = self.report()
            report['progress_diagnosis']['snapshots'][1][section][key] = value
            with self.assertRaises(ValueError):
                validate_stall(report, 'test', True)

    def test_return_or_wrong_trial_not_accepted(self):
        for output in (TRIGGER + '\nRVV_PERMUTE_RETURN', TRIGGER.replace('vl=32', 'vl=2')):
            report = self.report(); report['results'][0]['output'] = output
            with self.assertRaises(ValueError):
                validate_stall(report, 'test', True)


if __name__ == '__main__':
    unittest.main()
