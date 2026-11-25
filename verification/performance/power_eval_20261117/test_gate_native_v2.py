#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('successor', Path(__file__).with_name('gate_native_v2.py'))
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)


class Slots(unittest.TestCase):
    def test_actual_three_vcs_and_own_exclusion(self):
        rows = n.b.process_snapshot()
        sims = [pid for pid, (ppid, argv) in rows.items() if Path(argv[0]).name == 'simv']
        self.assertEqual(len(sims), 3, 'Reassess live capacity before launch')
        self.assertEqual(n.reserved_slots(rows), 3)
        rows[99999999] = (99999998, ['/tmp/simv'])
        self.assertEqual(n.reserved_slots(rows), 4)
        self.assertEqual(n.reserved_slots(rows, own_child=99999999), 3)

    def test_unknown_fail_closed(self):
        rows = {99: (1, ['python3', '/tmp/precheck_new.py', 'execute'])}
        self.assertEqual(n.reserved_slots(rows), 4)

    def test_v3_mutations_fail_closed(self):
        rows = n.b.process_snapshot()
        original = n.b.read
        for field, value in [('max_global_simv', 5), ('slot_lock', '/tmp/wrong'), ('parallel', 2)]:
            def mutated(path):
                data = original(path)
                if Path(path).name == 'plan.json' and 'max_global_simv' in data:
                    data[field] = value
                return data
            with patch.object(n.b, 'read', side_effect=mutated):
                self.assertEqual(n.reserved_slots(rows), 4)
        with patch.object(n.b, 'sha', return_value='0'*64):
            self.assertEqual(n.reserved_slots(rows), 4)

    def test_both_launch_locks(self):
        with n.slot_lock():
            self.assertTrue(n.SHARED.exists())


if __name__ == '__main__':
    unittest.main()
