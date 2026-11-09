#!/usr/bin/env python3
"""Host-only successor mapping, provenance, and checker rejection tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import run


def line(prefix, row):
    return prefix+' '+' '.join(f'{key}={value}' for key, value in row.items())+'\n'


def fixture(expected):
    text = line('VMFPU_ADAPTER_CONFIG', dict(shared_fma=0, checker_pipe_label=3))*4
    text += ''.join(line('PV_CLUSTER_FP_LANE', row) for row in expected['lanes'])
    text += ''.join(line('PV_CLUSTER_FP_CASE', row) for row in expected['groups'])
    text += ''.join(line('PV_CLUSTER_FP_STALL', dict(lane=l, request=1, write=1)) for l in range(4))
    n = expected['cases']
    ops = sum(row['issued'] for row in expected['lanes'])
    writes = sum(row['writes'] for row in expected['lanes'])
    text += line('PV_CLUSTER_FP_PASS', dict(cases=n, issued=ops, writes=writes, late=1,
        same=1, excess=1, max16=1, skew=1, done_stall=1, debt_terminal=1))
    owner = dict(native_done=5*n, acquires=n, releases=n, native_stalls=1, private_stalls=1,
        native_accepted=5*n, native_cancelled=0, private_issued=ops//4, private_returned=ops//4,
        private_cancelled=0, acquire_collisions=1, miter_cycles=1, native_grant_stalls=15*n,
        native_flag_events=n, reset_owned=0, native_fma=n, native_mul=n, native_div=n, native_max=n)
    text += line('VMFPU_OWNER_COVERAGE', owner)*4
    for row in expected['context']:
        cid = row['id']
        text += line('PV_CONTEXT_CASE', row)
        time = dict(id=cid, launch=1, first_coeff=2, first_read=3, last_read=4,
                    first_fma=5, last_fma=6, last_return=7, coeff_span=6, fma_span=3,
                    first_seed=2, last_seed=3, first_write=8, last_write=9, last_ack=10,
                    reader_done=5, cluster_done=11, drain=12, stream_stalls=1)
        text += line('PV_CONTEXT_TIME', time)
        text += line('PV_CONTEXT_START', dict(id=cid, owned=0, gate=15, ready=0))
        text += line('PV_CONTEXT_FIRST_FMA', dict(id=cid, owned=15, gate=15, ready=15))
        for lane in range(4):
            text += line('PV_CONTEXT_LANE_TIME', dict(id=cid, lane=lane, ready_stalls=2,
                preowner_stalls=1, owned_stalls=1, owned_cycles=5, native_cycles=4))
    text += line('PV_CONTEXT_PASS', dict(cases=n, **{key: sum(row[key] for row in expected['context'])
                for key in ('reads', 'coefficients', 'fills', 'latency')}))
    return text


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = run.upstream()
        cls.inputs = run.HERE/'upstream' if (run.HERE/'upstream').is_dir() else run.FP/'inputs'
        cls.expected, cls.files = run.selection(cls.inputs, cls.helper)
        generator = run.module(cls.inputs/'corpus.py')
        cls.records = generator.records((generator.BASE/'vectors/vectors.txt').read_text(),
            json.loads((generator.BASE/'vectors/vectors.json').read_text())['cases_by_id'])

    def test_exact_counts_and_coverage(self):
        e = self.expected
        self.assertEqual((e['cases'], len(e['lanes']), len(e['excluded'])), (66, 264, 35))
        self.assertEqual(sum(r['issued'] for r in e['lanes']), 36976)
        self.assertEqual(sum(r['writes'] for r in e['lanes']), 2544)
        self.assertEqual(sum(r['reads'] for r in e['context']), 5432)
        self.assertEqual(sum(r['coefficients'] for r in e['context']), 814)
        self.assertEqual(sum(r['fills'] for r in e['context']), 21728)
        self.assertEqual({r['source'] for r in e['mapping']}, set(range(33)))
        self.assertEqual({r['source'] for r in e['excluded']}, set(range(33, 68)))
        self.assertEqual([r['source'] for r in e['mapping'] if r['no_stalls']], [0, 1, 2])
        self.assertEqual({r['elements'] for r in e['mapping']}, {16, 24, 32})
        self.assertEqual({r['rm'] for r in e['mapping']}, set(range(5)))
        self.assertEqual({r['heads'] for r in e['mapping']}, {1, 2})

    def test_every_body_exact_original_with_only_header_id_remapped(self):
        for lane in range(4):
            lines = iter(self.files[f'lane{lane}.txt'].splitlines())
            self.assertEqual(next(lines), '50565531 66')
            for row in self.expected['mapping']:
                original = self.records[row['names'][lane]]
                header = original['header'][:]
                header[0] = str(row['id'])
                self.assertEqual(next(lines), ' '.join(header))
                self.assertEqual([next(lines) for _ in original['body']], original['body'])
            self.assertIsNone(next(lines, None))

    def test_distinct_real_lanes_both_synthetic_variants(self):
        for row in self.expected['mapping']:
            if row['source'] < 3:
                self.assertEqual(len(set(row['names'])), 4)
            else:
                self.assertEqual(len(set(row['names'])), 1)
                self.assertTrue(row['names'][0].startswith(f"matrix_{row['variant']}_"))

    def test_reject_original_unequal_broadcast_and_unsupported_tails(self):
        manifest = json.loads((self.inputs/'corpus.json').read_text())
        for row in manifest['groups'][3:]:
            with self.subTest(source=row['id']), self.assertRaises(ValueError):
                run.require_broadcast([self.records[n] for n in row['source_names']])

    def test_reject_wide_coefficient(self):
        row = copy.deepcopy(self.records['qwen3_tile0_lane0'])
        row['body'][int(row['header'][8])] = '0 0000000100000000'
        with self.assertRaisesRegex(ValueError, '32-bit'):
            run.require_broadcast([row]*4)

    def test_selected_body_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'upstream').symlink_to(self.inputs, target_is_directory=True)
            for name, value in self.files.items():
                (root/name).write_text(value)
            self.assertEqual(run.check_selected(root, self.helper), self.expected)
            path = root/'lane0.txt'
            path.write_text(path.read_text().replace('50565531 66', '50565531 65', 1))
            with self.assertRaisesRegex(ValueError, 'remap changed'):
                run.check_selected(root, self.helper)

    def test_normal_checker_and_context_records(self):
        result = run.check_log(fixture(self.expected), self.expected, self.helper)
        self.assertEqual(result['totals']['issued'], 36976)

    def test_reject_checker_mutations(self):
        text = fixture(self.expected)
        bad = [text.replace('coeff_span=6', 'coeff_span=5', 1),
               text.replace('fma_span=3', 'fma_span=4', 1),
               text.replace('reader_done=5', 'reader_done=11', 1),
               text.replace('latency=512', 'latency=511', 1),
               text.replace('preowner_stalls=1', 'preowner_stalls=0', 1),
               text.replace('native_done=330', 'native_done=329', 1),
               text.replace('reset_owned=0', 'reset_owned=1', 1),
               text.replace('returned=1024', 'returned=1023', 1),
               text.replace('PV_CONTEXT_START id=63 owned=0 gate=15',
                            'PV_CONTEXT_START id=63 owned=0 gate=0', 1),
               text.replace('PV_CONTEXT_FIRST_FMA id=0 owned=15 gate=15 ready=15\n', '', 1),
               text+line('PV_CONTEXT_CASE', self.expected['context'][0]),
               text+'Fatal: forced failure\n']
        for index, mutated in enumerate(bad):
            self.assertNotEqual(mutated, text)
            with self.subTest(index=index), self.assertRaises(ValueError):
                run.check_log(mutated, self.expected, self.helper)

    def test_service_output_excluded_even_json_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'stdout.json').write_text('still open')
            (root/'worker.log').write_text('still open')
            (root/'expected.json').write_text('{}')
            self.assertEqual(set(run.artifacts(root, self.helper)), {str(root/'expected.json')})

    def test_pin_conflict(self):
        with self.assertRaises(ValueError):
            run.merge({'doc.md': 'a'}, {'doc.md': 'b'})


if __name__ == '__main__':
    unittest.main()
