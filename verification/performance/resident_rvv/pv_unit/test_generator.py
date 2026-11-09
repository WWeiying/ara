"""Host tests for the oracle split, corpus, provenance, and strict run accounting."""
import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generate_vectors as gen
import run as runner


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = gen.reference()
        cls.rows = gen.cases(cls.ref, random_cases=2)

    def test_matrix(self):
        wanted = set(itertools.product(gen.ELEMENTS, (1, 2), gen.TOKENS, range(5)))
        for group in ('matrix_0_', 'matrix_1_'):
            actual = {(r['elements'], r['heads'], r['tokens'], r['rm'])
                      for r in self.rows if r['name'].startswith(group)}
            self.assertEqual(actual, wanted)
        self.assertIn(2, gen.ELEMENTS)

    def test_tail_mask_and_slot_order(self):
        row = gen.prepared_case(self.ref, 'tail', [[0]*31]*2,
                                [[0x3C00]]*2, [[0x3C00]*31], 0)
        self.assertEqual([s['slot'] for s in row['seeds']], list(range(16)))
        self.assertEqual([s['slot'] for s in row['commits']], list(range(16)))
        for op in row['ops']:
            self.assertEqual(op['mask'], 7 if op['slot'] % 8 == 7 else 15)
            self.assertEqual(op['flags'], 0)
        self.assertEqual(row['commits'][-1]['be'], 63)
        self.assertEqual(row['commits'][-1]['data'] >> 48, 0x7C01)

    def test_preparation_flags_not_charged_twice(self):
        row = next(r for r in self.rows if r['name'] == 'preparation_only_NV')
        self.assertEqual(row['prepared_flags'], 16)
        self.assertEqual(row['fma_flags'], 0)
        self.assertEqual(row['complete_flags'], 16)

    def test_exact_recurrence(self):
        row = gen.prepared_case(self.ref, 'exact', [[0]], [[0x3C00]*2], [[0x3C00]]*2, 0)
        self.assertEqual(row['output'], [[0x4000]])
        self.assertEqual(row['ops'][1]['c'] & 65535, 0x3C00)
        self.assertEqual(row['fma_flags'], 0)

    def test_flags_and_error_modes(self):
        flags = 0
        for r in self.rows:
            flags |= r['fma_flags']
        self.assertEqual(flags, 0b10111)  # FMA cannot raise divide-by-zero.
        self.assertEqual({r['mode'] for r in self.rows}, set(range(5)))
        self.assertEqual({r['reset_phase'] for r in self.rows if r['mode']==4}, {1, 3, 4})

    def test_deterministic(self):
        again = gen.cases(self.ref, random_cases=2)
        self.assertEqual(self.rows, again)

    def test_stream_counts_and_unique_operation_keys(self):
        for r in self.rows:
            if r['mode'] == 1:
                continue
            words=(r['elements']+3)//4
            self.assertEqual(len(r['ops']), words*r['heads']*r['tokens'])
            keys={(o['token'], o['slot']) for o in r['ops']}
            self.assertEqual(len(keys), len(r['ops']))
            if r['mode'] != 2:
                self.assertEqual(len(r['packets']), (words+1)*r['tokens'])
            else:
                self.assertEqual(len(r['packets']), r['bad_at']+1)
                self.assertNotEqual(r['packets'][-1]['kind'], int(r['bad_at']%(words+1)!=0))

    def test_shape_rejection(self):
        for rm in (-1, 5, 7):
            with self.assertRaises(ValueError):
                gen.prepared_case(self.ref, 'bad', [[0]], [[0]], [[0]], rm)
        with self.assertRaises(ValueError):
            gen.prepared_case(self.ref, 'bad', [[0]], [[0]], [[65536]], 0)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'vectors.txt'
            gen.write_vectors(p, self.rows[:1])
            before=p.read_bytes()
            with self.assertRaises(FileExistsError):
                gen.write_vectors(p, self.rows[:1])
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(int(p.read_text().split()[0], 16), gen.MAGIC)

    def test_real_validation(self):
        case=dict(name='recorded', heads=1, elements=1, tokens=1, rm=0,
                  seed=[[0]], coefficient=[[0x3C00]], values=[[0x3C00]],
                  expected=[[0x3C00]], flags=0)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'real.json'
            p.write_text(json.dumps(dict(cases=[case], artifacts={})))
            self.assertEqual(len(gen.real_cases(self.ref, p)), 1)
            for key, bad in (('flags', 16), ('expected', [[0]]), ('elements', 2)):
                changed=copy.deepcopy(case); changed[key]=bad
                p.write_text(json.dumps(dict(cases=[changed], artifacts={})))
                with self.assertRaises(ValueError):
                    gen.real_cases(self.ref, p)


class RunnerTests(unittest.TestCase):
    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'file'; p.write_text('initial')
            pins={str(p): runner.sha(p)}
            runner.verify(pins)
            p.write_text('modified')
            with self.assertRaises(ValueError):
                runner.verify(pins)

    def test_conflicting_aliases(self):
        pins={f'/verification/out/a/source/{p}': 'a'*64 for p in runner.SOURCES}
        pins['/verification/out/a/source/hardware/deps/common_cells/include/registers.svh']='a'*64
        pins[f'/verification/out/b/source/{runner.SOURCES[0]}']='b'*64
        with patch.object(runner, 'sha', return_value='a'*64):
            with self.assertRaisesRegex(ValueError, 'conflicting'):
                runner.dependency_selection(pins)

    def test_count_validation(self):
        case=dict(id=0, name='exact', mode=0, elements=1, heads=1, tokens=1, rm=0, fma_flags=0)
        corpus=dict(cases_by_id=[case])
        text=('PV_CASE_PASS id=0 mode=0 seeds=1 packets=2 issued=1 returned=1 commits=1 flags=0 cycles=20\n'
              'PV_UNIT_PASS cases=1 done=1 reset=0 issued=1 returned=1 cancelled=0 commits=1 cycles=20 pipe=3\n'
              'PV_COVERAGE request_stalls=1 stream_stalls=1 seed_stalls=0 result_stalls=1 done_stalls=1 '
              'raw_stalls=1 reordered=1 simultaneous=1 reset_pending=1 abort_pending=1 malformed_pending=1\n')
        self.assertEqual(runner.check_log(text, corpus, 3)['totals']['cases'], 1)
        for damaged in (text.replace('commits=1', 'commits=0'), text+text,
                        text.replace('flags=0', 'flags=16'), text.replace('reordered=1', 'reordered=0'),
                        text.replace('PV_UNIT_PASS', 'INCOMPLETE')):
            with self.assertRaises(ValueError):
                runner.check_log(damaged, corpus, 3)


if __name__ == '__main__':
    unittest.main()
