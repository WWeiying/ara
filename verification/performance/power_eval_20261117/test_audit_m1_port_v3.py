import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit_v3', Path(__file__).with_name('audit_m1_port_v3.py'))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class Tests(unittest.TestCase):
    def fixture(self):
        report = dict(first_tick=324290000, last_tick=539790000, duration_ticks=215500000, complete_initial_state=True)
        plan = dict(first_cycle=32414, last_cycle=53964)
        text = '''GATE_ROI_BEGIN cycle=32414 time=324290000
GATE_CAPTURE_WINDOW_COMPLETE cycle=53964 time=539790000 task_pass=0
$finish at simulation time 539790000
V C S   S i m u l a t i o n   R e p o r t
'''
        return report, text, plan

    def test_real_tick_units(self):
        proof = a.check_eof(*self.fixture())
        self.assertEqual(proof['timestamp_multiplier'], 1)
        self.assertEqual(proof['duration_fs'], 21550000000)

    def test_old_extra_conversion_rejected(self):
        report, text, plan = self.fixture()
        report['first_tick'] *= 10000
        report['last_tick'] *= 10000
        with self.assertRaises(ValueError):
            a.check_eof(report, text, plan)

    def test_bad_duration_rejected(self):
        report, text, plan = self.fixture()
        report['duration_ticks'] += 1
        with self.assertRaises(ValueError):
            a.check_eof(report, text, plan)

    def test_missing_finish_rejected(self):
        report, text, plan = self.fixture()
        with self.assertRaises(ValueError):
            a.check_eof(report, text.replace('$finish', 'missing'), plan)

    def test_task_completion_not_capture(self):
        report, text, plan = self.fixture()
        with self.assertRaises(ValueError):
            a.check_eof(report, text + 'Core Test FAILED\n', plan)


if __name__ == '__main__':
    unittest.main()
