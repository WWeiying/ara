#!/usr/bin/env python3
"""Host-only negative tests; never compile RTL or execute a component image."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('bank_resource_collector',
                                            Path(__file__).with_name('collect_weight_wide_bank.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checker = c.load_checker()
        cls.raw = (c.WORKER/'functional.log').read_bytes()
        cls.result = json.loads((c.WORKER/'result.json').read_bytes())
        names = dict(dut='qbs_weight_wide_bank.sv', mapper='qbs_weight_wide_mapper.sv',
                     assembler='qbs_weight_line_assembler.sv', pkg='qbs_pkg.sv',
                     payload='qbs_payload_sram.sv', tb='qbs_weight_wide_bank_tb.sv')
        cls.sources = {k:(c.WORKER/'source-snapshot'/v).read_text() for k,v in names.items()}
        cls.bill, cls.evidence = c.resource_bill(cls.sources)

    def test_original_fail_is_preserved(self):
        self.assertEqual(c.digest(c.WORKER/'result.json'), c.RESULT_SHA)
        self.assertEqual(c.digest(c.WORKER/'source-pins.json'), c.PINS_SHA)
        self.assertEqual(c.sha(self.raw), c.RAW_SHA)
        c.guard_worker(self.result)
        with self.assertRaisesRegex(ValueError, '^Actual resource declaration mismatch$'):
            self.checker.check(self.raw.decode())

    def test_exact_scoped_replay(self):
        projected, scope, measured = c.replay(self.raw, self.bill, self.checker)
        self.assertEqual(scope['version'], 2)
        self.assertEqual(set(scope['changes']), set(c.CHANGES))
        before, after = self.raw.decode().splitlines(), projected.splitlines()
        changed = [a for a,b in zip(before, after) if a != b]
        self.assertEqual(len(before), len(after))
        self.assertEqual(len(changed), 1)
        self.assertTrue(changed[0].startswith('WB_RESOURCE '))
        self.assertEqual(measured['totals']['cases'], 4608)
        self.assertEqual(measured['totals']['mixed_stalls'], 1526)
        self.assertEqual(measured['totals']['side_mixed_stalls'], 803)
        self.assertEqual(measured['totals']['max_drain'], 2)
        self.assertEqual(measured['totals']['unthrottled_stalls'], 0)

    def test_every_numeric_record_field_change_rejected(self):
        count = 0
        for line in self.raw.splitlines(keepends=True):
            if not line.startswith(b'WB_'):
                continue
            for match in re.finditer(rb'(?<==)\d+(?=\s|$)', line):
                changed = line[:match.start()]+str(int(match[0])+1).encode()+line[match.end():]
                raw = self.raw.replace(line, changed, 1)
                with self.subTest(record=line.split()[0], field=line[:match.start()].split()[-1]):
                    with self.assertRaisesRegex(ValueError, 'exact original raw trace'):
                        c.replay(raw, self.bill, self.checker)
                count += 1
        self.assertGreater(count, 1000)

    def test_every_record_deletion_rejected(self):
        records = [line for line in self.raw.splitlines(keepends=True) if line.startswith(b'WB_')]
        self.assertEqual(len(records), 156)
        for line in records:
            with self.subTest(record=line[:80]):
                with self.assertRaisesRegex(ValueError, 'exact original raw trace'):
                    c.replay(self.raw.replace(line, b'', 1), self.bill, self.checker)

    def test_other_raw_mutations_rejected(self):
        for raw in (self.raw+b'WB_UNKNOWN value=1\n', self.raw[:-1], self.raw+b'Fatal: bad\n',
                    self.raw.replace(b'WB_BANK_COMPONENT_PASS', b'WB_BANK_COMPONENT_FAIL')):
            with self.assertRaises(ValueError):
                c.replay(raw, self.bill, self.checker)

    def test_resource_projection_refuses_all_other_values(self):
        text = self.raw.decode()
        line = next(s for s in text.splitlines() if s.startswith('WB_RESOURCE '))
        for key, value in c.OBSERVED.items():
            bad = line.replace(key+'='+str(value), key+'='+str(value+1))
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'exact known unreliable'):
                    c.project_resource(text.replace(line, bad).encode(), self.bill, self.checker)
        for replacement in ('', line+'\n'+line, line+' extra=1', line+' mapper_packet_bits=948'):
            with self.assertRaises(ValueError):
                c.project_resource(text.replace(line, replacement).encode(), self.bill, self.checker)

    def test_static_bill_cannot_change_any_field(self):
        for key in self.bill:
            bad = dict(self.bill)
            bad[key] += 1
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'static resource bill mismatch'):
                    c.project_resource(self.raw, bad, self.checker)

    def test_original_worker_identity_fields_are_strict(self):
        for key, value in self.result.items():
            bad = copy.deepcopy(self.result)
            bad[key] = (not value if isinstance(value, bool) else
                        {} if isinstance(value, dict) else value+'changed')
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    c.guard_worker(bad)
        for key in self.result:
            bad = dict(self.result)
            del bad[key]
            with self.assertRaises(ValueError):
                c.guard_worker(bad)

    def test_resource_geometry_derivation(self):
        self.assertEqual(self.bill, self.checker.RESOURCES)
        self.assertEqual(self.bill['logical_sram_bytes'], 768)
        self.assertEqual(self.bill['target_sram_mc_physical_bytes'], 2048)
        self.assertEqual(self.bill['assembler_payload_bits'], 4096)
        self.assertEqual(self.evidence['geometry_assert_instances'], 8)
        self.assertEqual(self.evidence['four_row_normal_epochs'], 1152)
        self.assertEqual(sum(self.evidence['mapper_field_bits'].values()), 948)

    def test_static_type_and_witness_tampering_rejected(self):
        mutations = [('dut', 'r < 4', 'r < 3'), ('dut', 'p < 2', 'p < 1'),
                     ('dut', '.NumWords(p == 0 ? 4 : 2)', '.NumWords(p == 0 ? 8 : 2)'),
                     ('dut', 'side_q [4][20]', 'side_q [3][20]'),
                     ('mapper', 'logic [255:0] data;', 'logic [127:0] data;'),
                     ('assembler', '[255:0] carry_data_q', '[127:0] carry_data_q'),
                     ('pkg', '} qbs_weight_profile_e;', '} different_profile;'),
                     ('tb', 'WB_REAL_SRAM_GEOMETRY', 'REMOVED_ASSERT'),
                     ('tb', 'nrows<=4', 'nrows<=3'), ('tb', 'r*53', 'r*0'),
                     ('payload', '.Latency(1)', '.Latency(2)'),
                     ('payload', 'TS1N28HPCPUHDSVTB8X256', 'TS1N28HPCPUHDSVTB4X256')]
        for key, old, new in mutations:
            sources = dict(self.sources)
            self.assertIn(old, sources[key])
            sources[key] = sources[key].replace(old, new, 1)
            with self.subTest(source=key, old=old):
                with self.assertRaises(ValueError):
                    bill, _ = c.resource_bill(sources)
                    c.project_resource(self.raw, bill, self.checker)

    def test_missing_normal_coverage_still_fails_unchanged_checker(self):
        projected, _ = c.project_resource(self.raw, self.bill, self.checker)
        line = next(s for s in projected.splitlines() if s.startswith('WB_PROFILE_PASS '))
        with self.assertRaisesRegex(ValueError, 'Incomplete normal profile inventory'):
            self.checker.check(projected.replace(line+'\n', '', 1))
        for tag, old, new in [('WB_PROFILE_PASS ', 'cases=512', 'cases=511'),
                              ('WB_PROFILE_PASS ', 'unthrottled_stalls=0', 'unthrottled_stalls=1'),
                              ('WB_PROFILE_PASS ', 'max_drain=2', 'max_drain=4'),
                              ('WB_PROFILE_PASS ', 'reads=8192', 'reads=8191'),
                              ('WB_BANK_COMPONENT_PASS ', 'side_mixed_stalls=803', 'side_mixed_stalls=0')]:
            line = next(s for s in projected.splitlines() if s.startswith(tag))
            with self.subTest(old=old):
                self.assertIn(old, line)
                with self.assertRaises(ValueError):
                    self.checker.check(projected.replace(line, line.replace(old, new), 1))

    def test_fatal_return_zero_cannot_pass(self):
        projected, _ = c.project_resource(self.raw, self.bill, self.checker)
        for error in ('Fatal: bad', 'Error-[BAD]', 'Assertion xyz failed', 'UVM_ERROR bad'):
            with self.assertRaises(ValueError):
                self.checker.check(projected+'\n'+error+'\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
