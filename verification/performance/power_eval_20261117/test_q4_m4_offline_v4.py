"""Host-only large-UVM-context tests; semantic mutations retain all old gates."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('q4_offline_test', HERE/'q4_m4_offline_v4.py')
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
fixture_spec = importlib.util.spec_from_file_location('q4_actual_record_fixtures', HERE/'test_q4_m4_compact.py')
fixtures = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixtures)


class OfflineLogTests(unittest.TestCase):
    def scan_text(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'raw.log'
            path.write_text(text)
            return v4.scan(path)

    def test_verbose_context_does_not_change_actual_semantics(self):
        for mode in ('native', 'rvv'):
            m = fixtures.manifest(mode)
            m['power_records'] = 2
            compact = fixtures.synthetic_log(m)
            raw = ('UVM_INFO synthetic-context\n'*15000) + compact + ('UVM_INFO end-context\n'*5000)
            text, report = self.scan_text(raw)
            self.assertGreater(report['raw_bytes'], 262144)
            self.assertLess(report['retained_source_bytes'], 262144)
            self.assertTrue(report['every_raw_line_severity_checked'])
            self.assertFalse(report['synthesized_records'])
            self.assertEqual(text, compact)
            self.assertEqual(v4.old.parse_log(text, m)['state'], 'PASS')
            bad = fixtures.changed(compact, 'OPQ_TRIAL', 'vcsr', 0)
            with self.assertRaises(ValueError):
                v4.old.parse_log(self.scan_text(raw.replace(compact, bad))[0], m)

    def test_errors_in_discarded_context_never_disappear(self):
        compact = fixtures.synthetic_log(fixtures.manifest('rvv'))
        padding = 'UVM_INFO context\n'*20000
        for error in ('UVM_ERROR : 1', 'UVM_FATAL event', 'Error: broken', 'Fatal: bad',
                      'Assertion failed', '$fatal', '$error', 'TIMEOUT', 'unexpected FAILED'):
            for raw in (error+'\n'+padding+compact, padding+compact+error+'\n'):
                with self.subTest(error=error), self.assertRaises(ValueError):
                    self.scan_text(raw)

    def test_missing_duplicate_unknown_records_still_fail(self):
        m = fixtures.manifest('native')
        compact = fixtures.synthetic_log(m)
        for bad in (compact.replace('OPQ_DONE errors=0', ''), compact+'OPQ_DONE errors=0\n',
                    compact+'OPQ_UNKNOWN value=1\n', compact.replace('tohost = 0', 'tohost = 1')):
            with self.assertRaises(ValueError):
                v4.old.parse_log(self.scan_text(bad)[0], m)

    def test_known_failed_eoc_remains_failed_for_strict_checker(self):
        raw = 'Core Test *** FAILED *** (tohost = 1)\n'
        text, _ = self.scan_text(raw)
        self.assertEqual(text, raw)
        for bad in ('Core Test *** FAILED *** (tohost = 2)\n',
                    'unrelated FAILED '+raw):
            with self.assertRaises(ValueError):
                self.scan_text(bad)

    def test_resource_limits_apply_to_actual_records_and_lines(self):
        with mock.patch.object(v4, 'MAX_RECORD_BYTES', 20):
            with self.assertRaises(ValueError):
                self.scan_text('OPQ_DONE errors=0\n'*3)
        with mock.patch.object(v4, 'MAX_LINE_BYTES', 20):
            with self.assertRaises(ValueError):
                self.scan_text('UVM_INFO '+'x'*30+'\n')


if __name__ == '__main__':
    unittest.main()
