import importlib.util
from pathlib import Path
import unittest


def load(name):
    spec = importlib.util.spec_from_file_location('smol_successor_'+name, Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check, fixture = load('check_successor'), load('test_regression')
BANNER = 'Command: /sealed/simv +AKV_PERF'


class TestSuccessor(unittest.TestCase):
    def test_original_failure_is_reproduced_without_rewriting_log(self):
        text = BANNER+'\n'+fixture.hardware_log()
        with self.assertRaisesRegex(ValueError, 'Unknown/malformed'):
            check.original.check_hardware_work(text)
        self.assertEqual(check.check_hardware_work(text, BANNER)['commands'], 602)

    def test_other_text_cannot_hide_malformed_records(self):
        for prefix in ('unrecognized AKV_PERF', 'Command: /different/simv +AKV_PERF',
                       BANNER+'\n'+BANNER, ' [AKV_PERF] garbage'):
            with self.assertRaises(ValueError):
                check.check_hardware_work(prefix+'\n'+fixture.hardware_log(), BANNER)
        with self.assertRaises(ValueError):
            check.check_hardware_work(fixture.hardware_log(), BANNER)

    def test_fault_count_work_and_summary_checks_remain_enforced(self):
        for field in ('fault', 'validation_fault', 'read_fault', 'v2_rejected'):
            rows = fixture.command_rows()
            rows[3][field] = 1
            with self.assertRaises(ValueError):
                check.check_hardware_work(BANNER+'\n'+fixture.hardware_log(rows), BANNER)
        for rows in (fixture.command_rows()[:-1], fixture.command_rows()+fixture.command_rows()[-1:]):
            with self.assertRaises(ValueError):
                check.check_hardware_work(BANNER+'\n'+fixture.hardware_log(rows), BANNER)


if __name__ == '__main__':
    unittest.main()
