import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
from ucli_runtime_log_20261015 import classify_ucli_lines, iter_runtime_lines


SOURCE = '''if {[catch {
    puts "P_PROBE_READY"
    run
} failure]} {
    puts stderr "P_PROBE_REJECT $failure"
    exit 1
}
'''


class UcliRuntimeLogTest(unittest.TestCase):
    def runtime(self, log, source=SOURCE):
        return ''.join(iter_runtime_lines(log.splitlines(keepends=True), {'frozen.tcl': source}))

    def test_multiline_echo_then_real_reject(self):
        log = 'ucli% ' + SOURCE + 'P_PROBE_READY\nP_PROBE_REJECT Missing exact object x\n'
        self.assertEqual(self.runtime(log), 'P_PROBE_READY\nP_PROBE_REJECT Missing exact object x\n')

    def test_runtime_puts_is_not_blanket_filtered(self):
        log = 'puts stderr "P_PROBE_REJECT $failure"\n'
        self.assertEqual(self.runtime(log), log)

    def test_untrusted_prompt_is_not_filtered(self):
        log = 'ucli% puts "OTHER_PROBE_ERROR runtime"\n'
        self.assertEqual(self.runtime(log), log)

    def test_no_sources(self):
        log = 'ucli% ' + SOURCE
        self.assertEqual(''.join(iter_runtime_lines(log.splitlines(True), {})), log)

    def test_unprompted_source_is_runtime(self):
        self.assertEqual(self.runtime(SOURCE), SOURCE)

    def test_all_runtime_diagnostics_after_echo_survive(self):
        diagnostics = ('P_PROBE_ERROR missing object\nP_PROBE_REJECT capture full\n'
                       'Error: Tcl failed\nError-[BAD] VCS error\n'
                       'UVM_ERROR @ 0: reporter\nUVM_FATAL : 0\n'
                       'FATAL runtime failure\nCore Test *** FAILED ***\n')
        self.assertEqual(self.runtime('ucli% ' + SOURCE + diagnostics), diagnostics)

    def test_truncated_echo_is_not_filtered(self):
        log = 'ucli% ' + SOURCE[:-2]
        self.assertEqual(self.runtime(log), log)

    def test_interleaved_error_fails_closed(self):
        log = ('ucli% ' + SOURCE).replace('    run\n', 'Error: real failure\n    run\n')
        self.assertEqual(self.runtime(log), log)

    def test_whitespace_mismatch_fails_closed(self):
        log = ('ucli% ' + SOURCE).replace('    exit 1', ' exit 1')
        self.assertEqual(self.runtime(log), log)

    def test_incomplete_source_never_trusted(self):
        source = 'if {1} {\nputs P_PROBE_ERROR\n'
        log = 'ucli% ' + source
        self.assertEqual(self.runtime(log, source), log)

    def test_tcl_parser_handles_escaped_brace_and_continuation(self):
        source = 'set x "\\{quoted"\nset y [list one ' + '\\\n' + ' two]\n'
        log = 'ucli% set x "\\{quoted"\n{quoted\nucli% set y [list one ' + '\\\n' + ' two]\none two\n'
        self.assertEqual(self.runtime(log, source), '{quoted\none two\n')

    def test_no_tcl_evaluation(self):
        source = 'error "MUST NOT EXECUTE"\n'
        self.assertEqual(self.runtime('ucli% ' + source, source), '')

    def test_line_numbers_and_crlf(self):
        log = ('prefix\nucli% ' + SOURCE + 'P_PROBE_ERROR real\n').replace('\n', '\r\n')
        rows = list(classify_ucli_lines(log.splitlines(True), {'f': SOURCE}))
        self.assertEqual([r.number for r in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(sum(r.source_echo for r in rows), len(SOURCE.splitlines()))
        self.assertFalse(rows[-1].source_echo)


if __name__ == '__main__':
    unittest.main()
