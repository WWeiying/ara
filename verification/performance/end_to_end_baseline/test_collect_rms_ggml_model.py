#!/usr/bin/env python3
"""Host-only admission, raw-replay, graph, payload and archive negative tests."""
import copy
import struct
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import collect_rms_ggml_model as audit
from audit_sdk_guest_payload import EXPECTED_MODES, validate_payload
from rms_ggml_model import norm_work


def norm_text():
    lines = ['TRACE_CONTEXT_VARIANT_BEGIN variant=0', 'TRACE_CONTEXT_VARIANT_END variant=0',
             'TRACE_CONTEXT_VARIANT_BEGIN variant=1']
    for kind in range(2):
        for step in range(2):
            for (width, rows), count in audit.HISTOGRAMS[step].items():
                lines.extend([f'GGML_RISCV_RMS_EXEC enabled=1 fused=1 ith=0 nth=1 width={width} '
                              f'sum_fast={rows} sum_scalar=0 output_fast={rows} output_scalar=0'] * count)
            lines.append(f'OUTPUT_MODEL_STEP enabled=1 kind={kind} step={step} '
                         'token=32 fcsr=9 vcsr=5 outputs=151936')
    lines.append('TRACE_CONTEXT_VARIANT_END variant=1')
    return '\n'.join(lines)


def receipts():
    common = dict(baseline_library_sha256=audit.BASE_LIBRARY, candidate_library_sha256=audit.NEW_LIBRARY)
    elves = dict(baseline_elf_sha256=audit.BASE_ELF, candidate_elf_sha256=audit.CANDIDATE_ELF,
                 common_model_object_sha256=audit.MODEL_OBJECT)
    worker = dict(common, **elves, state='RMS_GGML_PREBUILT_MODEL_PAIR_FUNCTIONAL_PASS', child_pid=None,
                  compiled_translation_units=0, rtl_changed=False, performance_measured=False,
                  model_library_promoted=False, post_pins_match=True, post_path_identities_match=True,
                  reused_prebuilt_guest_payload=True, preflight=str(audit.PREFLIGHT),
                  preflight_result_sha256=audit.RECEIPTS[audit.PREFLIGHT])
    prepared = dict(common, **elves, state='RMS_GGML_MODEL_PAIR_PREPARED_NOT_EXECUTED', child_pid=None,
                    performance_measured=False, rtl_changed=False, production_library_promoted=False,
                    compiled_translation_units=1, common_model_object_reused=True, default_enabled=False,
                    baseline_link_reproduced_exactly=True, guest_cpio_parsed_and_bound=True,
                    library_build=str(audit.LIBRARY))
    library = dict(common, state='RMS_GGML_LIBRARY_BUILT_ARCHIVE_VERIFIED', target_executed=False,
                   performance_measured=False, rtl_changed=False, production_library_promoted=False,
                   default_enabled=False, member='ops.cpp.o', unchanged_other_members=31, members=32,
                   original_object_reproduced_exactly=True, public_exports_unchanged=True,
                   inventory_and_order_unchanged=True, original_library_unchanged=True,
                   post_pins_match=True, helpers_identical_to_measured_sources=True,
                   baseline_already_uses_ordered_rvv=True)
    return worker, prepared, library


def ar(members):
    result = bytearray(b'!<arch>\n')
    for name, data in members:
        header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{644:<8}{len(data):<10}`\n'.encode('ascii')
        assert len(header) == 60
        result.extend(header + data + (b'\n' if len(data) & 1 else b''))
    return bytes(result)


def elf(marker):
    data = bytearray(64)
    data[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', data, 16, 2, 243, 1)
    struct.pack_into('<H', data, 52, 64)
    return bytes(data) + marker


def newc(expected, extra=None):
    rows = [(name, mode, expected.get(name, b'')) for name, mode in EXPECTED_MODES.items()]
    if extra:
        rows.append(extra)
    result = bytearray()
    for index, (name, mode, data) in enumerate(rows + [('TRAILER!!!', 0, b'')]):
        trailer = name == 'TRAILER!!!'
        fields = [0 if trailer else index + 1, mode, 0, 0,
                  2 if mode & 0o170000 == 0o040000 else 1, 0, len(data), 0, 0,
                  5 if name == 'dev/console' else 0, 1 if name == 'dev/console' else 0,
                  len(name) + 1, 0]
        result.extend(b'070701' + ''.join(f'{value:08x}' for value in fields).encode('ascii'))
        result.extend(name.encode() + b'\0')
        result.extend(b'\0' * (-len(result) % 4))
        result.extend(data)
        result.extend(b'\0' * (-len(result) % 4))
    return bytes(result)


class CollectorTests(unittest.TestCase):
    def test_admission_exact(self):
        audit.admit(*receipts())

    def test_admission_rejects_terminal_and_identity_changes(self):
        for index, field, value in ((0, 'post_pins_match', False), (0, 'child_pid', 1),
                                    (0, 'state', 'RUNNING'), (1, 'default_enabled', True),
                                    (1, 'baseline_elf_sha256', audit.CANDIDATE_ELF),
                                    (2, 'unchanged_other_members', 30), (2, 'member', 'qbs.cpp.o')):
            with self.subTest(index=index, field=field):
                records = receipts()
                records[index][field] = value
                with self.assertRaises(ValueError):
                    audit.admit(*records)

    def test_admission_does_not_accept_zero_for_false(self):
        records = receipts()
        records[0]['performance_measured'] = 0
        with self.assertRaises(ValueError):
            audit.admit(*records)

    def test_exact_raw_node_histograms(self):
        result = audit.node_histograms(norm_work(norm_text()))
        self.assertEqual((result['operators'], result['sum_rows'], result['output_rows']), (452, 59622, 59622))
        self.assertEqual(result['fused_distribution'], {1: 452})
        self.assertEqual([row['sum_rows'] for row in result['steps']], [29082, 729, 29082, 729])

    def test_compensating_shape_change_rejected_despite_old_checker_pass(self):
        raw = norm_text().replace('sum_fast=640 sum_scalar=0 output_fast=640',
                                  'sum_fast=639 sum_scalar=0 output_fast=639', 1)
        raw = raw.replace('sum_fast=320 sum_scalar=0 output_fast=320',
                          'sum_fast=321 sum_scalar=0 output_fast=321', 1)
        # The old checker still accepts its node-count and aggregate-row gates.
        aggregate = norm_work(raw)
        with self.assertRaisesRegex(ValueError, 'histogram'):
            audit.node_histograms(aggregate)

    def test_nonfused_node_rejected_despite_old_checker_pass(self):
        raw = norm_text().replace('fused=1 ith=0 nth=1 width=128 sum_fast=640 sum_scalar=0 output_fast=640',
                                  'fused=0 ith=0 nth=1 width=128 sum_fast=640 sum_scalar=0 output_fast=0', 1)
        with self.assertRaisesRegex(ValueError, 'Nonfused'):
            audit.node_histograms(norm_work(raw))

    def test_node_sequence_types_and_missing_node(self):
        for change in ('sequence', 'type', 'missing'):
            norm = norm_work(norm_text())
            if change == 'sequence':
                norm['steps'][0]['kind'] = 1
            elif change == 'type':
                norm['steps'][0]['operators'][0]['fused'] = True
            else:
                norm['steps'][0]['operators'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit.node_histograms(norm)

    def test_raw_replay_is_mandatory_and_exact(self):
        native = dict(logits_compared=607744, comparisons=4, identical_full_logits=True,
                      identical_native_work=True, identical_tokens_and_csr=True, performance_measured=False)
        text = norm_text()
        measured = dict(native=native, norm=norm_work(text))
        with patch('trace_context_model.check', return_value=native) as checker:
            actual, hist = audit.replay_raw(text, 'CONTROL', ['SCHEMA'], measured, native)
            checker.assert_called_once_with(text, 'CONTROL', ['SCHEMA'])
            self.assertEqual(actual, measured)
            self.assertEqual(hist['operators'], 452)
        bad = copy.deepcopy(measured)
        bad['native']['logits_compared'] -= 1
        with patch('trace_context_model.check', return_value=native), self.assertRaises(ValueError):
            audit.replay_raw(text, 'CONTROL', ['SCHEMA'], bad, native)
        with patch('trace_context_model.check', side_effect=ValueError('native failure')), self.assertRaises(ValueError):
            audit.replay_raw(text, 'CONTROL', [], measured, native)

    def test_rms_failure_and_norm_incomplete_reject(self):
        with self.assertRaises(ValueError):
            audit.replay_raw('RMS_GGML_MODEL_FAIL', '', [], {}, {})
        with self.assertRaises(ValueError):
            norm_work(norm_text().rsplit('\n', 1)[0])

    def test_actual_archive_only_ops_replacement(self):
        old = [('ops.cpp.o', b'old')] + [(f'other{i}.o', b'fixed') for i in range(31)]
        new = [('ops.cpp.o', b'new')] + old[1:]
        rows = audit.archive_replay(ar(old), ar(new), b'new', b'old')
        self.assertEqual(sum(row['changed'] for row in rows), 1)
        for bad in (new[:-1], new[:1] + [('other0.o', b'changed')] + new[2:], old):
            with self.assertRaises(ValueError):
                audit.archive_replay(ar(old), ar(bad), b'new', b'old')
        with self.assertRaises(ValueError):
            audit.archive_replay(ar(old), ar(new), b'wrong', b'old')

    def test_newc_exact_elf_bytes_and_no_aa(self):
        expected = {name: elf(name.encode()) for name in ('init', 'base', 'candidate', 'test')}
        data = newc(expected)
        self.assertEqual(len(validate_payload(data, expected)['entries']), 8)
        bad = dict(expected, candidate=expected['base'])
        with self.assertRaises(ValueError):
            validate_payload(newc(bad), bad)
        bad = dict(expected, test=elf(b'wrong'))
        with self.assertRaises(ValueError):
            validate_payload(data, bad)

    def test_newc_truncated_extra_duplicate_and_traversal(self):
        expected = {name: elf(name.encode()) for name in ('init', 'base', 'candidate', 'test')}
        for data in (newc(expected)[:-8], newc(expected, ('extra', 0o100755, b'')),
                     newc(expected, ('test', 0o100755, expected['test'])),
                     newc(expected, ('../evil', 0o100755, b''))):
            with self.assertRaises(ValueError):
                validate_payload(data, expected)

    def test_unselected_qemu_source_is_not_read_or_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / 'receipt.json'
            selected.write_bytes(b'{}')
            absent_source = Path(directory) / 'qemu-source-does-not-exist.c'
            inventory = {str(selected): audit.digest(selected), str(absent_source): '0' * 64}
            pins = audit.ScopedPins(inventory, {str(selected): str(selected), str(absent_source): str(absent_source)})
            with patch.object(audit, 'digest', wraps=audit.digest) as hasher:
                pins.pin(selected)
                pins.verify()
                self.assertEqual([str(call.args[0]) for call in hasher.call_args_list], [str(selected), str(selected)])
            self.assertEqual(len(pins.values), 1)

    def test_selected_pin_hash_and_path_identity_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / 'raw.log'
            selected.write_bytes(b'raw')
            for inventory, identities in (({}, {}), ({str(selected): '0' * 64}, {str(selected): str(selected)}),
                                           ({str(selected): audit.digest(selected)}, {})):
                with self.assertRaises(ValueError):
                    audit.ScopedPins(inventory, identities).pin(selected)
            pins = audit.ScopedPins({str(selected): audit.digest(selected)}, {str(selected): str(selected)})
            pins.pin(selected)
            selected.write_bytes(b'drift')
            with self.assertRaises(ValueError):
                pins.verify()

    def test_candidate_link_changes_only_archive_and_output(self):
        base, candidate = Path('/old/lib.a'), Path('/new/lib.a')
        argv = ['g++', '-static', str(audit.PRIOR / 'model.o'), str(base), '-o',
                str(audit.PREFLIGHT / 'baseline-reproduced')]
        rows = [dict(label='reproduce-baseline', argv=argv, returncode=0, cwd=str(audit.PREFLIGHT), environment={}),
                dict(label='link-candidate', argv=argv[:3] + [str(candidate), '-o', str(audit.PREFLIGHT / 'candidate')],
                     returncode=0, cwd=str(audit.PREFLIGHT), environment={})]
        self.assertTrue(audit.link_pair(rows, base, candidate)['only_archive_and_output_differ'])
        rows[1]['argv'].insert(1, '-ffast-math')
        with self.assertRaises(ValueError):
            audit.link_pair(rows, base, candidate)


if __name__ == '__main__':
    unittest.main(verbosity=2)
