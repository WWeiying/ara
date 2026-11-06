"""Strict checker regressions; no EDA or old-helper execution."""
from pathlib import Path
import unittest

import run_weight_line_boundaries as target


def fatal_fixture(kind='overflow', dut='/sealed/qbs_weight_line_assembler.sv'):
    line, reason = target.REASONS[kind]
    return (f'Fatal: "{dut}", {line}: dut at time 65\n{reason}\n'
            f'$finish called from file "{dut}", line {line}.\n')


def normal_fixture():
    rows = []
    for width in target.WIDTHS:
        w, cases, streams, aborts, epochs, accepted, written, words = target.expected_width(width)
        rows.append(f'WEIGHT_LINE_BOUNDARIES_WIDTH_PASS width={w} cases={cases} '
                    f'streams={streams} aborts={aborts} epochs={epochs} '
                    f'accepted_bytes={accepted} written_bytes={written} word_writes={words}')
    return '\n'.join(rows + [target.TERMINAL]) + '\n'


class NormalTests(unittest.TestCase):
    def test_exact_widths_bytes_epochs_and_terminal(self):
        rows = target.check_normal(0, normal_fixture())
        self.assertEqual([r['width'] for r in rows], [6, 7, 8, 16])
        self.assertEqual(sum(r['cases'] for r in rows), 68)
        self.assertTrue(all(r['accepted_bytes']-r['written_bytes'] == 4 for r in rows))

    def test_missing_duplicate_malformed_or_wrong_terminal_rejected(self):
        text = normal_fixture()
        for wrong in ('\n'.join(text.splitlines()[1:]), text + target.TERMINAL,
                      text.replace('cases=68', 'cases=67'), text.replace('epochs=19', 'epochs=18'),
                      text + text.splitlines()[0] + '\n',
                      text + 'WEIGHT_LINE_BOUNDARIES_WIDTH_PASS malformed\n',
                      text + 'WEIGHT_LINE_BOUNDARIES_PASS malformed\n'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                target.check_normal(0, wrong)

    def test_any_fatal_error_or_assertion_and_bad_status_rejected(self):
        for diagnostic in ('Fatal: other_file.sv', 'fatal: other_file.sv', 'Error: tool failure',
                           'Assertion failed', "Offending 'guard'"):
            with self.subTest(diagnostic=diagnostic), self.assertRaises(ValueError):
                target.check_normal(0, normal_fixture() + diagnostic)
        with self.assertRaises(ValueError):
            target.check_normal(1, normal_fixture())


class NegativeTests(unittest.TestCase):
    def check(self, text, code=0, kind='overflow'):
        return target.contract_rejection(code, text, Path('/sealed/qbs_weight_line_assembler.sv'), kind)

    def test_zero_or_one_process_status_with_exact_guard(self):
        for kind in target.REASONS:
            for code in (0, 1):
                self.assertEqual(self.check(fatal_fixture(kind), code, kind)['global_fatals'], 1)

    def test_extra_global_fatal_from_other_file_is_rejected(self):
        text = fatal_fixture()
        for extra in ('Fatal: "/src/other.sv", 10: surprise\n',
                      'fatal: "/src/other.sv", 10: surprise\n',
                      fatal_fixture('empty'), 'prefix Fatal: unexpected\n'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check(text + extra)

    def test_missing_wrong_file_line_reason_finish_or_extra_diagnostic_rejected(self):
        text = fatal_fixture()
        for wrong in ('', text.replace('/sealed/', '/other/'), text.replace('132:', '131:'),
                      text.replace('exceeds its private bank', 'wrong reason'),
                      text + target.REASONS['overflow'][1] + '\n',
                      text.replace('$finish called', '$unknown called'),
                      text + '$finish called from file "/other.sv"\n',
                      text + 'BOUNDARIES_NEGATIVE_NOT_REJECTED', text + 'Error: failure',
                      text + target.TERMINAL, text + 'WEIGHT_LINE_COMPONENT_PASS'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                self.check(wrong)
        for code in (-9, 2, 139):
            with self.assertRaises(ValueError):
                self.check(text, code)


if __name__ == '__main__':
    unittest.main()
