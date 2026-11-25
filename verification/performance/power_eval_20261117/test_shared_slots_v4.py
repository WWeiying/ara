import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('slots_v4_test', HERE/'shared_slots_v4.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SharedSlotTests(unittest.TestCase):
    def legacy(self, reserve=0):
        return SimpleNamespace(KNOWN_DISPATCHERS={'precheck.py': 'pin', 'precheck_v2.py': 'pin'},
            dispatcher_reservation=lambda *args: reserve)

    def test_exact_conflict_replay_does_not_call_four_physical_processes(self):
        rows = {1: (0, ['python3', '/x/inputs/precheck_power_v3.py', 'execute', '--output', '/x']),
                2: (1, ['/image/sim/simv']), 3: (4, ['/gate/sim/simv'])}
        report = s.analyze(rows, self.legacy())
        self.assertEqual(report['physical_simv_count'], 2)
        self.assertEqual(report['committed_slots'], 2)
        self.assertEqual(report['blockers'][0]['kind'], 'UNKNOWN_DISPATCHER')
        with self.assertRaises(ValueError):
            s.admission(dict(protocol='RTL_GLS_SHARED_SLOTS_V4', cap=4, paused=False), report)
        original = s.adapter()
        self.assertEqual(original.reserved_slots(rows, own_child=3), 4)

    def test_pending_dispatch_is_reserved_without_double_counting(self):
        rows = {1: (0, ['python3', '/x/precheck_v2.py', 'execute', '--output', '/x']),
                2: (1, ['/image/sim/simv']), 3: (4, ['/gate/sim/simv'])}
        report = s.analyze(rows, self.legacy(reserve=3))
        self.assertEqual(report['legacy_future_reservations'], 2)
        self.assertEqual(report['committed_slots'], 4)
        with self.assertRaises(ValueError):
            s.admission(dict(protocol='RTL_GLS_SHARED_SLOTS_V4', cap=4, paused=False), report)

    def test_mixed_protocol_watchdog_is_a_barrier(self):
        for worker in ('gate_run.py', 'gate_run_baseline.py', 'gate_capture_baseline_v2.py'):
            report = s.analyze({1: (0, ['python3', '/inputs/'+worker, 'execute'])}, self.legacy())
            self.assertEqual(report['physical_simv_count'], 0)
            self.assertEqual(report['blockers'][0]['kind'], 'LEGACY_GLS_WATCHDOG_ACTIVE_MIGRATION_BARRIER')

    def test_lease_launch_race_and_visible_child_not_double_counted(self):
        lease = dict(id='RTL-1', owner_pid=1, state='LAUNCHING', child_pid=None,
                     command=['/image/sim/simv'])
        rows = {1: (0, ['python3', 'future_worker.py'])}
        report = s.analyze(rows, self.legacy(), [lease])
        self.assertEqual(report['committed_slots'], 1)
        lease.update(child_pid=2, state='RUNNING')
        rows[2] = (1, ['/image/sim/simv'])
        report = s.analyze(rows, self.legacy(), [lease])
        self.assertEqual(report['committed_slots'], 1)
        del rows[1]
        report = s.analyze(rows, self.legacy(), [lease])
        self.assertTrue(report['blockers'])
        self.assertEqual(report['physical_simv_count'], 1)

    def test_reused_child_is_not_an_available_slot(self):
        rows = {1: (0, ['python3', 'future_worker.py']), 2: (9, ['/different/simv'])}
        lease = dict(id='GLS-1', owner_pid=1, state='RUNNING', child_pid=2, command=['/gate/simv'])
        report = s.analyze(rows, self.legacy(), [lease])
        self.assertEqual(report['committed_slots'], 2)
        self.assertEqual(report['blockers'][0]['kind'], 'LEASE_CHILD_PID_REUSE_OR_COMMAND_DRIFT')

    def test_pause_and_full_capacity_never_admit(self):
        report = s.analyze({}, self.legacy())
        with self.assertRaises(ValueError):
            s.admission(dict(protocol='RTL_GLS_SHARED_SLOTS_V4', cap=4, paused=True), report)
        s.admission(dict(protocol='RTL_GLS_SHARED_SLOTS_V4', cap=4, paused=False), report)
        report['committed_slots'] = 4
        with self.assertRaises(ValueError):
            s.admission(dict(protocol='RTL_GLS_SHARED_SLOTS_V4', cap=4, paused=False), report)

    def test_unknown_controller_and_failed_snapshot_are_not_zero(self):
        report = s.analyze({1: (0, ['python3', '/x/after_compile.py'])}, self.legacy())
        self.assertTrue(report['blockers'])
        old = self.legacy()
        def fail(*args):
            raise ValueError('mixed snapshot')
        old.dispatcher_reservation = fail
        report = s.analyze({1: (0, ['python3', '/x/precheck.py', 'execute', '--output', '/x'])}, old)
        self.assertEqual(report['blockers'][0]['kind'], 'UNVERIFIABLE_DISPATCH_RESERVATION')


if __name__ == '__main__':
    unittest.main()
