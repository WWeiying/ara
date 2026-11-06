#!/usr/bin/env python3
"""Exact property-attribution audit, with global-fatal/origin mutation tests."""
from pathlib import Path
import tempfile
import unittest

import collect_wide_clients_scoped as c
from test_wide_clients import WideClientsTests


class ScopedOriginTests(unittest.TestCase):
    def source(self):
        return (c.original.MAIN/'hardware/src/vlsu/qbs_reader_narrow_view.sv').read_text()

    def log(self, dut):
        return (c.original.NEGATIVE_ARMED+'\n'+
                f'"{dut}", 51: {c.INSTANCE}: started at 35000ps failed at 35000ps\n'+
                "\tOffending '((wide_i.data_strb >> 16) == 0)'\n"+
                f'Fatal: "{dut}", 51: {c.INSTANCE}: at time 35000 ps\n'+
                c.original.NEGATIVE_REASON+'\n'+
                f'$finish called from file "{dut}", line 51.\n')

    def test_binding_exact(self):
        b = c.bind_property(self.source())
        self.assertEqual((b['property_line'], b['fatal_action_line']), (51, 53))

    def test_binding_rejects_changed_predicate_reason_or_line(self):
        source = self.source()
        for bad in (source.replace('>> 16', '>> 15'), source.replace('wide_i.data_valid |->', '1 |->'),
                    source.replace(c.original.NEGATIVE_REASON, 'OTHER_REASON'), '\n'+source,
                    source+'\nassert property (1);\n'):
            with self.assertRaises(ValueError):
                c.bind_property(bad)

    def test_projection_changes_only_fatal_header_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            dut = Path(tmp)/'qbs_reader_narrow_view.sv'; dut.write_text(self.source())
            raw = self.log(dut)
            for code in (0, 1):
                evidence, projection = c.scoped_negative(code, raw, dut)
                self.assertEqual(evidence['global_fatals'], 1)
                self.assertEqual(projection, raw.replace(f'Fatal: "{dut}", 51:', f'Fatal: "{dut}", 53:', 1))
                self.assertTrue(evidence['original_negative_gates_replayed'])

    def test_negative_all_other_origins_lines_and_extra_fatals_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dut = Path(tmp)/'qbs_reader_narrow_view.sv'; dut.write_text(self.source())
            raw = self.log(dut)
            for bad in (raw.replace(str(dut), '/foreign/other.sv'), raw.replace(', 51:', ', 50:'),
                        raw.replace(', 51:', ', 53:'), raw.replace('line 51.', 'line 53.'),
                        raw.replace(c.INSTANCE, 'qbs_wide_clients_tb.copy128.dut.unnamed$$_2'),
                        raw+'Fatal: "unrelated.sv", 1: wrong\n', raw+'fAtAl: extra\n',
                        raw.replace('35000', '45000'), raw.replace('>> 16', '>> 17'),
                        raw.replace(c.original.NEGATIVE_REASON, 'WRONG_REASON'), raw+raw,
                        raw+'PASS\n', raw+c.original.TERMINAL+'\n', raw+'Error: other\n',
                        raw.replace(c.original.NEGATIVE_ARMED, ''), raw.replace('\tOffending', 'Offending')):
                with self.assertRaises(ValueError):
                    c.scoped_negative(0, bad, dut)
            with self.assertRaises(ValueError):
                c.scoped_negative(2, raw, dut)

    def test_original_checker_failure_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            dut = Path(tmp)/'qbs_reader_narrow_view.sv'; dut.write_text(self.source())
            with self.assertRaisesRegex(ValueError, c.RAW_ERROR):
                c.original.check_negative(0, self.log(dut), dut)


if __name__ == '__main__':
    unittest.main()
