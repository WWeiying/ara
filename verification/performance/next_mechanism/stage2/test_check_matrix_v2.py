#!/usr/bin/env python3
"""Use matrix01's actual console records, including the missed multi-word heads."""
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
import check_matrix_v2 as c


class ConsoleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = c.legacy()
        cls.text = (c.ORIGINAL / 'baseline/context.log').read_text()
        cls.cases = cls.old.vectors((c.ORIGINAL / 'context_baseline.txt').read_text())

    def check(self, text):
        return c.check_log(text, self.cases, 0, 'context')

    def test_reproduces_real_failure(self):
        with self.assertRaisesRegex(ValueError, 'Malformed/duplicate log field'):
            self.old.check_log(self.text, self.cases, 0, 'context')

    def test_actual_context_console(self):
        result = self.check(self.text)
        self.assertEqual(len(result['cycles']), 12)
        self.assertEqual(len(result['commands']), 372)
        for key in ('phases', 'fp', 'traffic'):
            self.assertEqual(len(result[key]), 12)
        self.assertEqual(result['totals']['reset_commands'], 12)

    def test_all_actual_record_heads(self):
        for prefix in c.SCHEMAS:
            line = next(line for line in self.text.splitlines() if line.startswith(prefix))
            self.assertEqual(set(c.parse_fields(line)), set(c.SCHEMAS[prefix].split()))

    def test_synthetic_still_checked(self):
        for arm, enable in (('baseline', 0), ('candidate', 1)):
            text = (c.ORIGINAL / arm / 'synthetic.log').read_text()
            cases = self.old.vectors((c.ORIGINAL / f'synthetic_{arm}.txt').read_text())
            self.assertEqual(len(c.check_log(text, cases, enable, 'synthetic')['cycles']), 36)

    def test_duplicate_field_rejected(self):
        with self.assertRaises(ValueError):
            self.check(self.text.replace('setup=9 ', 'setup=9 setup=9 ', 1))

    def test_extra_nonfield_rejected(self):
        with self.assertRaises(ValueError):
            self.check(self.text.replace('setup=9 ', 'setup=9 unexpected ', 1))

    def test_missing_unknown_and_punctuated_fields(self):
        for replacement in ('', 'alien=9 ', 'setup=9, ', 'setup:9 '):
            with self.assertRaises(ValueError):
                self.check(self.text.replace('setup=9 ', replacement, 1))

    def test_no_arbitrary_prefix_skipping(self):
        with self.assertRaises(ValueError):
            c.parse_fields('unknown header case=0 setup=9')

    def test_missing_or_duplicate_probe(self):
        line = next(line for line in self.text.splitlines() if line.startswith('QBS FP probe '))
        for changed in (self.text.replace(line + '\n', '', 1), self.text.replace(line, line + '\n' + line, 1)):
            with self.assertRaises(ValueError):
                self.check(changed)

    def test_pass_colon_and_finish_punctuation(self):
        self.assertIn('QBS engine PASS: 12 functional cases\n', self.text)
        self.assertIn('$finish called from file "', self.text)
        self.check(self.text)

    def test_late_failure_rejected(self):
        for marker in ('Fatal: bad data', 'Error-[SVA] failure', '$fatal(1)', 'Assertion failed'):
            with self.assertRaises(ValueError):
                self.check(self.text + marker + '\n')

    def test_native_work_not_relaxed(self):
        with self.assertRaises(ValueError):
            self.check(self.text.replace('native_products=32768', 'native_products=32767', 1))

    def test_original_report_identity(self):
        self.assertEqual(c.sha(c.ORIGINAL / 'report.json'), c.REPORT_SHA)
        self.assertEqual(json.loads((c.ORIGINAL / 'report.json').read_text())['state'], 'FAIL')

    def test_full_offline_pin_audit(self):
        report = c.audit_original()
        self.assertEqual(report['state'], 'OFFLINE_RECHECK_PASS_PARTIAL')
        self.assertEqual(report['source_pins_checked'], 171)
        self.assertEqual(report['image_pins_checked'], dict(baseline=40, candidate=40))


if __name__ == '__main__':
    unittest.main(verbosity=2)
