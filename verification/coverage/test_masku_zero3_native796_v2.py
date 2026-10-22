import itertools
import json
from pathlib import Path
import tempfile
from types import FunctionType
import unittest
from unittest.mock import patch

import masku_zero3_native796_v2 as v
import test_masku_zero3_native796 as original_tests


class GroupedRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = v.read_bound(v.REVIEW, v.REVIEW_SHA)
        cls.c = dict(instances=v.compiled(cls.review))
        cls.inst = next(i for i in cls.c['instances'] if i['scope'] == v.SCOPE)
        cls.header = ['CHECKSUM: "%s %s"' % (cls.inst['design_checksum'], cls.inst['toggle_checksum']),
                      'INSTANCE: ' + v.SCOPE]
        cls.annotation = 'ANNOTATION: "' + v.ANNOTATION + '"'
        cls.toggles = ['Toggle %s "logic %s[255:0]"' % (n, n) for n in v.NAMES]
        cls.actual = v.FIRST.read_text()
        cls.ptw = v.read_bound(v.FIRST_CONFIG, v.FIRST_CONFIG_SHA)['instances'][0]
        cls.ptw_members = {s['name']: 'logic ' + s['name'] +
                           ('[%d:%d]' % (s['left'], s['right']) if s['kind'] == 'vectornode' else '')
                           for s in cls.ptw['signals']}
        cls.ptw_annotation = 'RVH0 direct combinational g_content and VMID zero outputs only; unknown internal H state protected'

    def ptw_records(self, text):
        return v.parse_records(text, self.ptw['scope'], '%s %s' %
                               (self.ptw['design_module_checksum'], self.ptw['toggle_checksum']),
                               self.ptw_members, self.ptw_annotation)

    def grouped(self, toggles=None, annotation_index=0, repeat=1):
        lines = list(self.toggles if toggles is None else toggles)
        lines[annotation_index:annotation_index] = [self.annotation] * repeat
        return '\n'.join(self.header + lines) + '\n'

    def test_real_ptw_one_header12_toggle_late_annotation(self):
        self.assertEqual(self.actual.count('CHECKSUM:'), 1)
        self.assertEqual(self.actual.count('INSTANCE:'), 1)
        self.assertEqual(sum(l.startswith('Toggle ') for l in self.actual.splitlines()), 12)
        self.assertGreater(self.actual.index('ANNOTATION:'), self.actual.index('Toggle '))
        result = self.ptw_records(self.actual)
        self.assertEqual({r[2] for r in result}, set(self.ptw_members))
        self.assertEqual(len(result), 12)
        self.assertEqual(v.digest(v.FIRST), v.FIRST_SHA)

    def test_real_ptw_annotation_front_middle_end_and_repeated_same(self):
        lines = [l for l in self.actual.splitlines() if not l.startswith('ANNOTATION:')]
        expected = self.ptw_records(self.actual)
        annotation = 'ANNOTATION: "' + self.ptw_annotation + '"'
        for index in range(2, len(lines) + 1):
            self.assertEqual(self.ptw_records('\n'.join(lines[:index] + [annotation] * 2 + lines[index:])), expected)

    def test_three_grouped_all_object_orders_annotation_positions(self):
        expected = v.records(self.grouped(), self.c)
        for toggles in itertools.permutations(self.toggles):
            for index in range(4):
                for repeat in (1, 2, 3):
                    with self.subTest(toggles=toggles, index=index, repeat=repeat):
                        self.assertEqual(v.records(self.grouped(toggles, index, repeat), self.c), expected)

    def test_original_repeated_headers_and_grouped_have_same_semantics(self):
        repeated = '\n'.join(l for toggle in self.toggles for l in self.header + [self.annotation, toggle])
        self.assertEqual(v.records(repeated, self.c), v.records(self.grouped(annotation_index=3), self.c))
        with self.assertRaises(ValueError): v.old.records(self.grouped(annotation_index=2), self.c)

    def test_missing_wrong_annotation_cannot_be_borrowed_across_blocks(self):
        good = self.grouped()
        bad = [good.replace(self.annotation, ''), good.replace(v.ANNOTATION, 'wrong'),
               good + 'ANNOTATION: "wrong"\n', '\n'.join([self.header[0], self.annotation, self.header[1]] + self.toggles),
               '\n'.join(self.header + [self.annotation, self.toggles[0]] + self.header + self.toggles[1:]),
               '\n'.join(self.header + [self.toggles[0]] + self.header + [self.annotation] + self.toggles[1:])]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ValueError): v.records(text, self.c)

    def test_scopeextra_headers_checksums_and_empty_blocks(self):
        good = self.grouped()
        mutations = [good.replace(v.SCOPE, v.PARENT), good.replace(v.SCOPE, v.SCOPE + '.extra'),
                     good.replace('1400516067', '0'), good.replace('4132557224', '0'),
                     good + 'INSTANCE: ' + v.SCOPE + '\n', good + '\n'.join(self.header) + '\n',
                     good + '\n'.join(self.header + [self.annotation]) + '\n',
                     good + 'CHECKSUM: "4132557224 1400516067"\nINSTANCE: foreign\n',
                     '\n'.join(self.header[1:] + self.toggles + [self.annotation]), '']
        for text in mutations:
            with self.subTest(text=text), self.assertRaises(ValueError): v.records(text, self.c)

    def test_partial_directions_metrics_declarations_and_extra_members(self):
        good = self.grouped()
        for text in [good.replace('[255:0]', '[254:0]'), good.replace('[255:0]', '[255:1]'),
                     good.replace('Toggle ', 'Toggle 0to1 '), good.replace('Toggle ', 'Toggle 1to0 '),
                     good.replace('Toggle ', 'Line '), good.replace('logic ', 'wire '),
                     good.replace('bit_enable_mask_o', 'bit_enable_mask'),
                     good + 'Branch unexpected\n', good + 'Toggle foreign "logic foreign[255:0]"\n',
                     good.replace('Toggle bit_enable_mask_o ', 'Toggle bit_enable_mask_o [0] '),
                     self.grouped(self.toggles[:2])]:
            with self.subTest(text=text), self.assertRaises(ValueError): v.records(text, self.c)

    def test_duplicates_same_block_and_across_headers(self):
        good = self.grouped()
        for text in [good + self.toggles[0] + '\n', good + good,
                     self.grouped([self.toggles[0], self.toggles[0], self.toggles[2]])]:
            with self.subTest(text=text), self.assertRaises(ValueError): v.records(text, self.c)

    def test_real_ptw_wrong_missing_annotation_partial_and_duplicate_rejected(self):
        lines = self.actual.splitlines()
        toggle = next(l for l in lines if l.startswith('Toggle '))
        for text in [self.actual.replace(self.ptw_annotation, 'wrong'),
                     '\n'.join(l for l in lines if not l.startswith('ANNOTATION:')),
                     self.actual.replace('[43:0]', '[42:0]'), self.actual + toggle + '\n',
                     self.actual + 'INSTANCE: foreign\n', self.actual.replace('Toggle ', 'Toggle 0to1 ')]:
            with self.subTest(text=text), self.assertRaises(ValueError): self.ptw_records(text)

    def test_rebound_five_phase_el_gates_use_grouped_parser(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            for stage in v.STAGES:
                (out / v.FILES[stage]).write_text(self.grouped(annotation_index=2) if stage == 'selected' else
                                                self.grouped(annotation_index=3, repeat=2) if stage == 'reloaded' else '')
                v.check_el(out, self.c, stage)
            self.assertEqual(v.check_el(out, self.c, 'selected'), v.check_el(out, self.c, 'reloaded'))

    def test_frozen_original_and_private_successor_entry(self):
        self.assertEqual(v.digest(v.old.__file__), v.OLD_SHA)
        self.assertIs(v.check_el.__globals__['records'], v.records)
        self.assertEqual(v.inspect.__globals__['ENTRY'], v.ENTRY)
        self.assertEqual(v.prepare.__globals__['__file__'], v.__file__)
        self.assertIn('test_masku_zero3_native796_v2.py', v.contract.__closure__[0].cell_contents.__code__.co_consts)

    def test_no_native_qualification_from_parser_or_mock_done(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            v.save(out / 'terminal.json', dict(returncode=0, timeout=False, actual_dve=[]))
            v.save(out / 'execution.json', {})
            v.save(out / 'live-identity.json', [])
            with patch.dict(v.inspect.__globals__, verify=lambda *_: self.c):
                with self.assertRaises(ValueError): v.inspect(out, 'model-only')
            self.assertFalse((out / 'capture-result.json').exists())


# Rebind the frozen gate tests privately; do not modify their module or the helper.
class PreservedNativeGates(unittest.TestCase):
    pass


_test_globals = dict(vars(original_tests), m=v)
for _name, _method in vars(original_tests.NativeTests).items():
    if _name == 'test_no_native_done_only_qualification':
        continue
    if isinstance(_method, classmethod):
        _fn = _method.__func__
        setattr(PreservedNativeGates, _name, classmethod(FunctionType(_fn.__code__, _test_globals, _name, _fn.__defaults__)))
    elif isinstance(_method, FunctionType):
        setattr(PreservedNativeGates, _name, FunctionType(_method.__code__, _test_globals, _name, _method.__defaults__))


if __name__ == '__main__': unittest.main()
