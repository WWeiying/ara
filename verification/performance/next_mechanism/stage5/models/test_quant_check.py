"""Fail-closed quant accounting, frozen TB semantics, and read-only quiet02 replay."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import quant_check as qc


def record(tag, values):
    return tag + ' ' + ' '.join(k + '=' + str(v) for k, v in values.items()) + '\n'


def fixture(spec=None):
    spec = qc.SHAPE if spec is None else spec
    lines = []
    for m in (0, 1):
        for s in range(3):
            identity = dict(case=spec['id'], requested=m, step=s)
            lines.append(record('STAGE5_STEP_BEGIN', dict(identity,
                input_rows=40 if s == 0 else 1, logical_context=40 + s)))
            lines.append(record('BIND_COUNTER', dict(identity, when='before')))
            for _ in range(28):
                lines.extend(record(t, v) for t, v in qc.expected_records(spec, s))
            lines.append(record('BIND_COUNTER', dict(identity, when='after')))
            lines.append(record('STAGE5_STEP_END', identity))
    return lines


class QuantRecords(unittest.TestCase):
    def test_workspace_sizeof_formulas(self):
        self.assertEqual(qc.workspace_sizes(), dict(prefill=22464, decode=13120))

    def test_both_fixed_specs_and_row_byte_formulas(self):
        for case, block in (('qwen25_q4kv', 18), ('qwen25_q8kv', 34)):
            spec = qc.SHAPES[case]
            with self.subTest(case=case):
                prefill = qc.expected_records(spec, 0)[0][1]
                self.assertEqual(prefill['key_bytes'], 1260 * 4 * block)
                self.assertEqual(prefill['workspace'], 22464)
                self.assertEqual(prefill['commands'], 184)
                rows = qc.quant_records(fixture(spec), spec)
                self.assertEqual([r['commands'] for r in rows], [5152, 224, 224] * 2)
                for step in (1, 2):
                    layout = qc.expected_records(spec, step)[1][1]
                    self.assertEqual(layout['k_head_stride'], 4 * block)
                    self.assertEqual(layout['k_token_stride'], 8 * block)
                    self.assertEqual(layout['key_bytes'], 2 * (40 + step) * 4 * block)
                    self.assertEqual(layout['workspace'], 13120)

    def test_ready_q8_spec_and_cross_encoding_rejection(self):
        spec = qc.read(qc.OUT/'stage5_models_execution_final_qwen25q8_20261110_02/spec.json')
        rows = qc.quant_records(fixture(spec), spec)
        self.assertEqual([r['commands'] for r in rows], [5152, 224, 224] * 2)
        self.assertEqual(qc.expected_records(spec, 0)[0][1]['key_bytes'], 171360)
        for case, wrong in (('qwen25_q4kv', 'q8_0'), ('qwen25_q8kv', 'q4_0')):
            bad = dict(qc.SHAPES[case], cache_k=wrong)
            with self.subTest(case=case), self.assertRaises(ValueError):
                qc.expected_records(bad, 0)
        bad = fixture(spec)
        old = record(*qc.expected_records(spec, 0)[0])
        bad[bad.index(old)] = record(*qc.expected_records(qc.SHAPE, 0)[0])
        with self.assertRaises(ValueError):
            qc.quant_records(bad, spec)

    def test_formula_not_observed_excess(self):
        prefill = qc.expected_records(qc.SHAPE, 0)[0][1]
        self.assertEqual((prefill['commands'], prefill['groups'],
                          prefill['value_decodes'], prefill['queries_quantized'],
                          prefill['key_bytes'], prefill['workspace']),
                         (184, 60, 1260, 480, 90720, 22464))
        for step in (1, 2):
            decode = qc.expected_records(qc.SHAPE, step)
            self.assertEqual(decode[0][1]['command_attempts'], 8)
            self.assertEqual(decode[0][1]['value_decodes'], 2 * (40 + step))
            self.assertEqual(decode[1][1]['key_bytes'], 144 * (40 + step))
            self.assertEqual(decode[1][1]['key_panels'], 4)

    def test_complete_identical_arms(self):
        rows = qc.quant_records(fixture(), qc.SHAPE)
        self.assertEqual([r['commands'] for r in rows], [5152, 224, 224] * 2)
        self.assertEqual(sum(r['commands'] for r in rows), 11200)

    def test_every_quant_field_is_exact(self):
        for spec in qc.SHAPES.values():
            lines = fixture(spec)
            for s in range(3):
                for tag, values in qc.expected_records(spec, s):
                    for key, value in values.items():
                        with self.subTest(case=spec['id'], step=s, tag=tag, field=key):
                            changed = dict(values)
                            changed[key] = value + 1
                            bad = list(lines)
                            i = bad.index(record(tag, values))
                            bad[i] = record(tag, changed)
                            with self.assertRaises(ValueError):
                                qc.quant_records(bad, spec)

    def test_layer_missing_extra_and_wrong_phase(self):
        lines = fixture()
        for s in range(3):
            tag, values = qc.expected_records(qc.SHAPE, s)[0]
            i = lines.index(record(tag, values))
            for change in ('missing', 'extra', 'wrong_phase'):
                with self.subTest(step=s, change=change):
                    bad = list(lines)
                    if change == 'missing':
                        del bad[i]
                    elif change == 'extra':
                        bad.insert(i, bad[i])
                    else:
                        bad[i] = record(*qc.expected_records(qc.SHAPE, (s + 1) % 3)[0])
                    with self.assertRaises(ValueError):
                        qc.quant_records(bad, qc.SHAPE)

    def test_decode_layout_order(self):
        lines = fixture()
        i = next(i for i, line in enumerate(lines) if line.startswith('GGML_RISCV_QUANT_KV '))
        lines[i + 1], lines[i + 2] = lines[i + 2], lines[i + 1]
        with self.assertRaises(ValueError):
            qc.quant_records(lines, qc.SHAPE)

    def test_unscoped_before_after_terminal(self):
        lines = fixture()
        quant = record(*qc.expected_records(qc.SHAPE, 0)[0])
        for index in (0, 1, len(lines) - 1, len(lines)):
            with self.subTest(index=index):
                bad = list(lines)
                bad.insert(index, quant)
                with self.assertRaises(ValueError):
                    qc.quant_records(bad, qc.SHAPE)

    def test_malformed_duplicate_unknown_fields_and_tag(self):
        lines = fixture()
        i = 2
        for bad_line in (lines[i].replace('status=0', 'status=-1'),
                         lines[i].replace('status=0', 'status=00'),
                         lines[i].replace('status=0 ', ''),
                         lines[i].rstrip() + ' status=0\n',
                         lines[i].rstrip() + ' extra=0\n',
                         lines[i].replace(' status=', ' status=='),
                         lines[i].replace('QUANT_PREFILL', 'QUANT_UNKNOWN'),
                         'prefix ' + lines[i], ' ' + lines[i]):
            with self.subTest(line=bad_line):
                bad = list(lines)
                bad[i] = bad_line
                with self.assertRaises(ValueError):
                    qc.quant_records(bad, qc.SHAPE)

    def test_phase_identity_order_shape_and_snapshot(self):
        lines = fixture()
        for i in (0, 1, 30, 31):
            for key, old, new in (('requested', '0', '1'), ('step', '0', '1'),
                                  ('case', 'qwen25_q4kv', 'other')):
                with self.subTest(index=i, key=key):
                    bad = list(lines)
                    bad[i] = bad[i].replace(key + '=' + old, key + '=' + new)
                    with self.assertRaises(ValueError):
                        qc.quant_records(bad, qc.SHAPE)
        for index in (1, 30):
            bad = list(lines)
            del bad[index]
            with self.assertRaises(ValueError):
                qc.quant_records(bad, qc.SHAPE)

    def test_unsupported_shape_and_incomplete_pair(self):
        for key in qc.SHAPE:
            spec = copy.deepcopy(qc.SHAPE)
            spec[key] = None
            with self.subTest(key=key), self.assertRaises(ValueError):
                qc.quant_records(fixture(), spec)
        with self.assertRaises(ValueError):
            qc.quant_records(fixture()[:-1], qc.SHAPE)
        with self.assertRaises(ValueError):
            qc.quant_records(fixture() + fixture(), qc.SHAPE)


class NativeAccounting(unittest.TestCase):
    def setUp(self):
        self.quant = qc.quant_records(fixture(), qc.SHAPE)
        self.entries = {(m, s): dict(qbs=n, pv_prepare=0)
                        for m in (0, 1) for s, n in enumerate((401148, 45292, 45292))}
        self.result = dict(phases=[dict(requested=m, step=s, architectural={})
                                  for m in (0, 1) for s in range(3)],
                           qbs={'Q4_0': dict(native_qbexec=486132)})

    def test_exact_not_allowance(self):
        result = qc.reconcile(self.result, self.entries, self.quant)
        self.assertEqual([r['quant_commands'] for r in result], [5600, 5600])
        self.assertEqual([r['native_entries'] for r in result], [491732, 491732])
        for delta in (-1, 1, 5600):
            bad = copy.deepcopy(self.entries)
            for m in (0, 1):
                bad[(m, 0)]['qbs'] += delta
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                qc.reconcile(self.result, bad, self.quant)

    def test_same_total_different_arm_phases_rejected(self):
        self.entries[(1, 0)]['qbs'] += 1
        self.entries[(1, 1)]['qbs'] -= 1
        with self.assertRaises(ValueError):
            qc.reconcile(self.result, self.entries, self.quant)

    def test_pv_and_binding_phase_integrity(self):
        self.entries[(1, 0)]['pv_prepare'] = 1
        with self.assertRaises(ValueError):
            qc.reconcile(self.result, self.entries, self.quant)
        self.result['phases'].pop()
        with self.assertRaises(ValueError):
            qc.reconcile(self.result, self.entries, self.quant)

    def test_frozen_stopped_tb_semantics(self):
        base = qc.load(qc.HERE/'prefill_check.py', qc.PREFILL_SHA, 'quant_test_entries')
        symbols = dict(qbs_native_execute_command=(0x100, 0x110),
                       akv_experimental_resident_pv_prepare=(0x200, 0x210))
        begin = ['STAGE5_STEP_BEGIN requested=0 step=0\n', 'BIND_COUNTER when=before\n']
        trace = 'Trace 0: 0xabc [000/100/0/0] qbs\n'
        stop = 'Stopped execution of TB chain before 0xabc [100] reason\n'
        counts = base.native_entries(begin + [trace, stop, trace], symbols)
        self.assertEqual(counts[(0, 0)]['qbs'], 1)
        self.assertEqual(base.native_entries.stopped[(0, 0)]['qbs'], 1)
        for invalid in (begin + [stop], begin + [trace, stop.replace('[100]', '[104]')],
                        [trace], begin + [trace.replace('Trace 0:', 'Trace 1:')],
                        begin + [trace.replace('/100/', '/300/')]):
            with self.subTest(lines=invalid), self.assertRaises(ValueError):
                base.native_entries(invalid, symbols)


class SourceAndReplay(unittest.TestCase):
    def test_compiled_formula_and_manifest_identity(self):
        dependencies = qc.compiled_sources()
        for path in (qc.BUILD/'build.json', qc.BUILD/'compiler-dependencies.json',
                     qc.BUILD/'build/compile_commands.json', qc.PREPARED/'source-pins.json',
                     qc.INPUTS/'llama/ggml/src/ggml-cpu/arch/riscv/qbs.cpp',
                     qc.INPUTS/'llama/ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp',
                     qc.INPUTS/'sdk/software/akv/experimental/quantized_kv/prefill/prefix_schedule.h',
                     qc.INPUTS/'sdk/software/akv/experimental/quantized_kv/register_pv/runtime.c'):
            self.assertIn(str(path), dependencies)
            original_sha = qc.sha
            def drift(p):
                return '0' * 64 if p == path else original_sha(p)
            with self.subTest(path=path), patch.object(qc, 'sha', side_effect=drift):
                with self.assertRaisesRegex(ValueError, 'drift'):
                    qc.compiled_sources()

    def test_frozen_checker_drift(self):
        with self.assertRaisesRegex(ValueError, 'drift'):
            qc.load(qc.HERE/'prefill_check.py', '0' * 64, 'invalid_quant_source')

    def test_frozen_content_still_rejects_missing_logits(self):
        execution = qc.OUT/'stage5_models_execution_final_qwen25q4_20261110_02'
        assets = qc.OUT/'stage5_models_launch_assets_qwen25q4_20261110_02'
        content = qc.load(execution/'inputs/binding_check.py', qc.BINDING_SHA,
                          'quant_negative_full_content')
        def damaged(stream):
            skipped = False
            for line in stream:
                if not skipped and line.startswith('BIND_LOGITS '):
                    skipped = True
                    continue
                yield line
        with (execution/'guest.log').open() as stream:
            with self.assertRaisesRegex(ValueError, 'Logit range/order'):
                content.check_lines(damaged(stream), qc.read(execution/'spec.json'),
                                    qc.read(assets/'pcs.json'))

    def test_read_only_quiet02_full_content_and_mapped_native_pcs(self):
        execution = qc.OUT/'stage5_models_execution_final_qwen25q4_20261110_02'
        assets = qc.OUT/'stage5_models_launch_assets_qwen25q4_20261110_02'
        before = qc.sha(execution/'result.json')
        class View:
            def __truediv__(self, name):
                return (assets if name in ('pcs.json', 'symbols.json') else execution)/name
        def mapped(value):
            return View() if str(value) == str(execution) else Path(value)
        with patch.object(qc, 'Path', side_effect=mapped):
            result = qc.check(str(execution))
        self.assertEqual(result['state'], 'CONTENT_CHECKED_NOT_ACCEPTED')
        self.assertEqual(result['logits_compared'], 455808)
        self.assertEqual([r['commands'] for r in result['quant_phase_commands']], [5152, 224, 224] * 2)
        self.assertEqual([r['native_entries'] for r in result['native_command_accounting']], [491732] * 2)
        self.assertFalse(result['instruction_retirement_claim'])
        self.assertFalse(result['rtl_or_model_speed_claim'])
        self.assertEqual(qc.read(execution/'result.json')['state'], 'FAIL')
        self.assertEqual(before, qc.sha(execution/'result.json'))


if __name__ == '__main__':
    unittest.main()
