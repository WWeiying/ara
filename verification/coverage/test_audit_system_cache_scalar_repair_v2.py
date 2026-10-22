"""Real cache04 log mutations; originals remain read-only. No subprocesses."""
import unittest
from unittest.mock import patch

import audit_system_cache_scalar_repair_v2 as a


class RealScalarLog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logs = [(a.DIRECTORY / name).read_text() for name in ('console.log', 'run.vcs.log')]
        cls.vector = (a.DIRECTORY / 'vector_trace.csv').read_text()

    def setUp(self):
        for name in ('subprocess.run', 'subprocess.Popen'):
            guard = patch(name, side_effect=AssertionError('offline only'))
            guard.start()
            self.addCleanup(guard.stop)

    def test_both_real_logs_only_functional_pass_not_uvm_clean(self):
        results = [a.check_log(log, a.old.ELF_SHA) for log in self.logs]
        self.assertEqual(results[0], results[1])
        self.assertFalse(results[0]['uvm_clean'])
        self.assertEqual(results[0]['uvm_error_count'], 2)
        self.assertTrue(all(x == 0 for x in results[0]['contract'].values()))

    def test_original_checker_still_rejects_real_two_errors(self):
        for log in self.logs:
            with self.assertRaisesRegex(ValueError, 'UVM error/fatal diagnostic'):
                a.old.check_log(log)

    def test_no_blanket_other_elf_exception(self):
        with self.assertRaisesRegex(ValueError, 'exact original scalar ELF'):
            a.check_log(self.logs[0], '0' * 64)

    def test_missing_duplicate_or_changed_allowed_error_rejected(self):
        log = self.logs[0]
        first = next(l for l in log.splitlines() if l.startswith('UVM_ERROR ') and '[CVXIF/NO_TRAFFIC]' in l)
        for bad in (log.replace(first, ''), log + first + '\n',
                    log.replace('scoreboard observed no complete CVXIF traffic', 'scoreboard protocol failure'),
                    log.replace('ara_cvxif_uvm_pkg.sv(504)', 'other.sv(504)')):
            with self.subTest(tail=bad[-60:]), self.assertRaises(ValueError):
                a.check_log(bad, a.old.ELF_SHA)

    def test_unrelated_uvm_error_and_fatal_rejected(self):
        for extra in ('UVM_ERROR x.sv(1) @ 1: test [AXI/BAD] mismatch\n',
                      'UVM_FATAL x.sv(1) @ 1: test [BAD] broken\n',
                      'UVM_ERROR: hidden diagnostic\n'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                a.check_log(self.logs[0] + extra, a.old.ELF_SHA)

    def test_summary_counts_must_be_exact(self):
        log = self.logs[0]
        for old, new in (('UVM_ERROR :    2', 'UVM_ERROR :    0'),
                         ('UVM_ERROR :    2', 'UVM_ERROR :    3'),
                         ('UVM_FATAL :    0', 'UVM_FATAL :    1'),
                         ('[VID/NO_TRAFFIC]     1', '[VID/NO_TRAFFIC]     2')):
            self.assertIn(old, log)
            with self.subTest(old=old, new=new), self.assertRaises(ValueError):
                a.check_log(log.replace(old, new), a.old.ELF_SHA)

    def test_vector_and_axi_activity_rejected(self):
        log = self.logs[0]
        for old, new in (('observed requests=0', 'observed requests=1'),
                         ('allocations=0', 'allocations=1'),
                         ('ar=0 r_beats=0', 'ar=1 r_beats=1'),
                         ('aw=0 w_beats=0', 'aw=1 w_beats=1'),
                         ('hold_checks=0', 'hold_checks=1'),
                         ('protocol_errors=0', 'protocol_errors=1')):
            self.assertIn(old, log)
            with self.subTest(old=old), self.assertRaises(ValueError):
                a.check_log(log.replace(old, new), a.old.ELF_SHA)

    def test_any_other_assertion_or_error_rejected(self):
        for extra in ('Assertion failed at x.sv:1\n', 'Error: corrupt\n', 'Fatal-[BAD] stop\n',
                      '$fatal: broken\n', 'ERROR unexpected\n', 'Watchdog timeout\n',
                      'Core Test *** FAILED ***\n'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                a.check_log(self.logs[0] + extra, a.old.ELF_SHA)

    def test_incomplete_or_wrong_software_check_rejected(self):
        for old, new in (('checks=1758', 'checks=1172'),
                         ('Core Test *** SUCCESS ***', 'no terminal'),
                         ('$finish called from file', 'missing finish')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                a.check_log(self.logs[0].replace(old, new), a.old.ELF_SHA)

    def test_native_vector_trace_is_config_only(self):
        a.check_vector(self.vector)
        for bad in (self.vector + self.vector.splitlines()[1] + '\n',
                    self.vector.replace(',config,', ',alloc,'), self.vector.splitlines()[0] + '\n'):
            with self.assertRaisesRegex(ValueError, 'no native vector'):
                a.check_vector(bad)


if __name__ == '__main__':
    unittest.main()
