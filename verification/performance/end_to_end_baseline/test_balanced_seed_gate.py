"""Host-only seed gate source, work-model and raw-admission negative tests."""
from pathlib import Path
import json
import re
import unittest
from unittest.mock import patch

import balanced_seed_gate as g


def emit(tag, **values):
    return tag + ' ' + ' '.join(key + '=' + (f'{value:08x}' if key in ('a', 'b', 'c', 'bits') else str(value))
                              for key, value in values.items())


def fake_log(shapes, split, zero_m4=False):
    """A parser fixture, not a numerical simulator or target-execution claim."""
    lines = [f'BSG_CONFIG ingress=128 matrix=1 balanced=1 seed_restore=1 split={split}']
    for s in shapes:
        cid = s['case']
        if cid < 2:
            lines.append(f'QBS_SEED_CANCEL_PASS reset={cid}')
        nonzero = 0
        for acc, bits in s['outputs'].items():
            for k in range(s['kb']):
                checkpoint = 0 if zero_m4 and s['m'] == 4 else 0x3f800000 + cid * 512 + acc + k
                if split and k:
                    lines.append(emit('BSG_CHECKPOINT', case=cid, k=k, acc=acc, bits=checkpoint))
                    lines.append(emit('BSG_SEED', case=cid, k=k, acc=acc, bits=checkpoint))
                    nonzero += checkpoint != 0
                lines.append(emit('BSG_REQUEST', case=cid, acc=acc, k=k, first=int(k == 0)))
                lines.append(emit('BSG_ACCUM', case=cid, acc=acc, k=k, state=4,
                                  a=0x3f800000, b=0x40000000, c=checkpoint if k else 0))
                if s['profile'] in (1, 4, 7):
                    lines.append(emit('BSG_ACCUM', case=cid, acc=acc, k=k, state=5,
                                      a=0xbf800000, b=0x3f800000, c=0x3f000000))
            lines.append(emit('BSG_OUTPUT', case=cid, acc=acc, bits=bits))
        lines.append(f"QBS command case {cid} PASS profile={s['profile']} M={s['m']} N={s['n']} "
                     f"Kb={s['kb']} layouts={s['wl']}/{s['al']}")
        lines.append(emit('BSG_CASE', case=cid, profile=s['profile'], m=s['m'], n=s['n'], kb=s['kb'],
                          flags=s['flags'], **dict(zip(g.COUNTERS, s['counters'])),
                          checkpoints=len(s['outputs']) * (s['kb'] - 1) * split, nonzero=nonzero,
                          recovery=1 if cid == 0 else 2 if cid == 1 else 0))
    lines.append('QBS command fault discard PASS')
    lines.extend(f'QBS pipeline fault stage {stage} PASS drain_cycles=3' for stage in range(4))
    lines.append(f"QBS_CONTINUATION_ACCEPT split={split} prefixes={sum(s['kb'] - 1 for s in shapes) * split}")
    lines.append('QBS command engine PASS: 36 functional cases')
    return '\n'.join(lines) + '\n'


class SeedGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = g.TB.read_text()
        cls.helper = g.CONTINUATION.read_text()
        cls.inherited = g.inherited_bench(cls.original, cls.helper)
        cls.bench, cls.report = g.bench_source(cls.original, cls.helper)
        cls.raw = g.RAW36.read_text()
        if g.sha(cls.raw.encode()) != g.RAW36_SHA:
            raise ValueError('Unit fixture differs from accepted independent C oracle')
        cls.converted, cls.shapes = g.vectors(cls.raw)
        cls.unsplit = fake_log(cls.shapes, 0)
        cls.split = fake_log(cls.shapes, 1)

    def test_exact_original_sources_and_reversible_child_edits(self):
        self.assertEqual(g.sha(self.original.encode()), g.TB_SHA)
        self.assertEqual(g.sha(self.helper.encode()), g.CONTINUATION_SHA)
        text = self.bench
        for edit in reversed(self.report['edits']):
            self.assertEqual(text.count(edit['after']), 1)
            text = text.replace(edit['after'], edit['before'], 1)
        self.assertEqual(text, self.inherited)
        self.assertTrue(self.report['original_bench_source_reused'])

    def test_source_drift_fails_closed(self):
        for template, helper in ((self.original + '\n', self.helper), (self.original, self.helper + '\n'),
                                 ('', self.helper), (self.original, '')):
            with self.assertRaises(ValueError):
                g.bench_source(template, helper)

    def test_actual_seed_parameters_and_original_tasks(self):
        for item in (".SeedRestoreEnable(1'b1)", ".WideWeightIngress(1'b0)",
                     ".WideMatrixDot(1'b1)", ".BalancedMatrixDot(1'b1)",
                     'qbs_compute_engine_balanced', 'BSG_SEED_NOT_WRITTEN',
                     'BSG_FIRST_BLOCK_OR_OWNER', 'BSG_RESTORED_ADDEND_CHANGED', 'BSG_ZERO_M4_CHECKPOINT'):
            self.assertIn(item, self.bench)
        original_task = self.inherited.split('  task automatic seed_fault_or_reset', 1)[1].split('  endtask', 1)[0]
        new_task = self.bench.split('  task automatic seed_fault_or_reset', 1)[1].split('  endtask', 1)[0]
        self.assertEqual(new_task, original_task)
        self.assertIn('if(ordinal==0) seed_fault_or_reset(0)', self.bench)
        self.assertIn('if(ordinal==1) seed_fault_or_reset(1)', self.bench)
        for marker in ('command counter/flags mismatch', 'output %0d got=', 'QBS_SEED_CANCEL_PASS reset=',
                       'QBS command fault discard PASS', 'check_pipeline_fault(stage)'):
            self.assertIn(marker, self.bench)

    def test_only_capacity_dot_fields_change_in_original_36(self):
        old, new = self.raw.splitlines(), self.converted.splitlines()
        self.assertEqual(len(old), len(new))
        for a, b in zip(old, new):
            if not a.startswith('C '):
                self.assertEqual(a, b)
            else:
                aa, bb = a.split(), b.split()
                for index in (0, 1, 2, 3, 4, 7, 8):
                    self.assertEqual(aa[index], bb[index])
        self.assertEqual(len(self.shapes), 36)
        self.assertEqual({s['profile'] for s in self.shapes}, set(range(1, 10)))
        self.assertEqual(sum(s['kb'] - 1 for s in self.shapes), 362)

    def test_balanced_work_theory_independent_of_vector_rewrite(self):
        for shape in self.shapes:
            m, n, kb = shape['m'], shape['n'], shape['kb']
            block = 256 if shape['profile'] in (1, 2, 4, 5, 7) else 32
            issues = 0
            for first in range(0, m, 4):
                wave = min(4, m - first)
                step = 8 if wave == 1 or block == 256 and wave >= 3 else 4 if wave == 2 else 2
                issues += len(range(0, block, step))
            self.assertEqual(shape['counters'][4], n * kb * issues * 32)
            self.assertEqual(shape['counters'][5], len(range(0, n, 4)) * kb * issues)

    def test_complete_raw_pair_admission(self):
        report = g.check_pair(self.unsplit, self.split, self.shapes)
        self.assertEqual(report['state'], g.SUCCESS)
        self.assertGreater(report['split']['m4_nonzero_checkpoint_words'], 0)
        self.assertEqual(report['split']['prefixes'], 362)
        self.assertFalse(report['performance_measured'])

    def test_saved_json_shapes_replay_without_losing_integer_owners(self):
        saved = json.loads(json.dumps(self.shapes))
        report = g.check_pair(self.unsplit, self.split, saved)
        self.assertEqual(report['state'], g.SUCCESS)
        saved[0]['outputs']['00'] = saved[0]['outputs']['0']
        with self.assertRaises(ValueError):
            g.check_log(self.unsplit, saved, 0)

    def test_reject_fatal_return_zero_style_and_missing_terminal(self):
        for bad in (self.split + 'Fatal: failure\n', self.split + 'Error-[ASSERT] failure\n',
                    self.split.replace('QBS command engine PASS: 36 functional cases', ''),
                    self.split.replace('QBS_SEED_CANCEL_PASS reset=1', ''),
                    self.split.replace('QBS pipeline fault stage 3 PASS drain_cycles=3', '')):
            with self.assertRaises(ValueError):
                g.check_pair(self.unsplit, bad, self.shapes)

    def test_zero_only_m4_payload_cannot_claim_continuation(self):
        zero = fake_log(self.shapes, 1, zero_m4=True)
        with self.assertRaisesRegex(ValueError, 'Zero-only M4'):
            g.check_log(zero, self.shapes, 1)

    def test_missing_seed_or_changed_actual_writeback_rejected(self):
        seed = next(line for line in self.split.splitlines() if line.startswith('BSG_SEED '))
        for bad in (self.split.replace(seed + '\n', '', 1),
                    self.split.replace(seed, seed[:-1] + ('1' if seed[-1] != '1' else '2'), 1)):
            with self.assertRaises(ValueError):
                g.check_log(bad, self.shapes, 1)

    def test_seed_write_must_precede_continued_request(self):
        lines = self.split.splitlines()
        seed = next(line for line in lines if line.startswith('BSG_SEED '))
        words = dict(word.split('=') for word in seed.split()[1:])
        request = f"BSG_REQUEST case={words['case']} acc={words['acc']} k={words['k']} first=0"
        lines.remove(seed)
        index = lines.index(request)
        lines.insert(index + 1, seed)
        with self.assertRaisesRegex(ValueError, 'temporal order'):
            g.check_log('\n'.join(lines), self.shapes, 1)

    def test_first_block_continuation_and_fma_addend_rejected(self):
        request = next(line for line in self.split.splitlines() if line.startswith('BSG_REQUEST ') and ' k=1 ' in line)
        fma = next(line for line in self.split.splitlines() if line.startswith('BSG_ACCUM ') and ' k=1 state=4 ' in line)
        for bad in (self.split.replace(request, request.replace('first=0', 'first=1'), 1),
                    self.split.replace(fma, re.sub(r'c=[0-9a-f]+', 'c=00000000', fma), 1)):
            with self.assertRaises(ValueError):
                g.check_log(bad, self.shapes, 1)

    def test_changed_output_flags_or_counter_rejected(self):
        output = next(line for line in self.split.splitlines() if line.startswith('BSG_OUTPUT '))
        summary = next(line for line in self.split.splitlines() if line.startswith('BSG_CASE '))
        for bad in (self.split.replace(output, output[:-1] + ('1' if output[-1] != '1' else '2'), 1),
                    self.split.replace(summary, summary.replace('flags=1', 'flags=0'), 1),
                    self.split.replace(summary, re.sub(r'dot=\d+', 'dot=0', summary), 1)):
            self.assertNotEqual(bad, self.split)
            with self.assertRaises(ValueError):
                g.check_log(bad, self.shapes, 1)

    def test_reset_cannot_mask_fault_recovery(self):
        lines = self.split.splitlines()
        lines.remove('QBS_SEED_CANCEL_PASS reset=1')
        lines.insert(1, 'QBS_SEED_CANCEL_PASS reset=1')
        with self.assertRaisesRegex(ValueError, 'Reset masks'):
            g.check_log('\n'.join(lines), self.shapes, 1)

    def test_pair_rejects_operands_changed_even_with_correct_final_output(self):
        event = next(line for line in self.unsplit.splitlines() if line.startswith('BSG_ACCUM '))
        changed = self.unsplit.replace(event, event.replace('a=3f800000', 'a=3f800001'), 1)
        with self.assertRaisesRegex(ValueError, 'FMA operands'):
            g.check_pair(changed, self.split, self.shapes)

    def test_execution_requires_explicit_exact_preparation_receipt(self):
        with self.assertRaises(ValueError):
            g.execute(g.OUT, None)
        with self.assertRaises(ValueError):
            g.execute(Path('/tmp/not-the-sealed-seed-gate'), '0' * 64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
