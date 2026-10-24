"""Bounded host tests. Optional final-artifact audit never recomputes graphs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

import prepare_tail_gold as p


def transcript(kind='q8_0'):
    return ''.join(f'TAIL_GOLD_OUTPUT kind={kind} visible={v} outputs=1536 bytes=6144 '
                   f'baseline={int(v == 128)} max_abs={"1e-06" if v == 128 else "0"} inputs_unchanged=1\n'
                   for v in (128, 5, 33)) + f'TAIL_GOLD_PASS kind={kind} graphs=3 outputs_per_graph=1536 reference=archived_host_ggml\n'


class TailGoldTest(unittest.TestCase):
    def test_real_metadata_and_archive_receipts(self):
        receipt, original, pins, captures = p.checked_archive()
        self.assertEqual(receipt['state'], 'REAL_HOST_QUANTIZED_KV_CAPTURED')
        self.assertTrue(original)
        self.assertEqual(set(captures), set(p.KINDS))
        p.verify(pins)

    def test_metadata_mutations(self):
        for kind in p.KINDS:
            row = 72 if kind == 'q4_0' else 136
            meta = dict(type=kind, shape=[128, 256, 2, 1], strides=[row//4, row, 256*row, 512*row], nbytes=512*row)
            self.assertEqual(p.metadata_check(meta, kind, 'k'), 512*row)
            for key, value in (('type', 'f16'), ('shape', [128, 256, 1, 1]),
                               ('shape', [128, 128, 2, 1]), ('nbytes', 512*row-1),
                               ('strides', [row//4, row*2, row, row*512])):
                bad = copy.deepcopy(meta)
                bad[key] = value
                with self.subTest(kind=kind, key=key, value=value), self.assertRaises(ValueError):
                    p.metadata_check(bad, kind, 'k')

    def test_pin_drift_and_conflict(self):
        with tempfile.TemporaryDirectory(prefix='tail-gold-pins-') as tmp:
            path = Path(tmp) / 'input.bin'
            path.write_bytes(b'original')
            pins = {}
            p.pin(pins, path)
            p.verify(pins)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                p.verify(pins)
            with self.assertRaises(ValueError):
                p.pin(pins, path)

    def test_exact_reference_protocol(self):
        for kind in p.KINDS:
            self.assertEqual(p.parse_reference(transcript(kind), kind), {'128': 1e-6, '5': 0.0, '33': 0.0})
        text = transcript()
        mutations = [text.replace('visible=5 ', 'visible=33 ', 1),
                     text.replace('bytes=6144', 'bytes=6140', 1),
                     text.replace('max_abs=1e-06', 'max_abs=nan', 1),
                     text.replace('max_abs=1e-06', 'max_abs=1e999', 1),
                     text.replace('baseline=0 max_abs=0', 'baseline=0 max_abs=0.01', 1),
                     text.replace('inputs_unchanged=1', 'inputs_unchanged=0', 1),
                     text.replace('reference=archived_host_ggml', 'reference=qbs_ref'),
                     text + text.splitlines()[0] + '\n',
                     '\n'.join(text.splitlines()[1:]),
                     text + 'TAIL_GOLD_FAIL reason=bad\n']
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                p.parse_reference(bad, 'q8_0')

    def test_output_extent_finiteness_and_shape(self):
        with tempfile.TemporaryDirectory(prefix='tail-gold-output-') as tmp:
            path = Path(tmp) / 'q8_0-v5.bin'
            raw = struct.pack('<1536f', *(i/1024 for i in range(1536)))
            path.write_bytes(raw)
            record = p.output_record(path, 'q8_0', 5)
            self.assertEqual(record['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(record['shape'], [128, 12, 1, 1])
            self.assertEqual(record['bytes'], 6144)
            self.assertFalse(record['native_execution'])
            for bad in (raw[:-4], raw+b'\0', struct.pack('<I', 0x7f800001)+raw[4:], struct.pack('<I', 0x7f800000)+raw[4:]):
                path.write_bytes(bad)
                with self.assertRaises(ValueError):
                    p.output_record(path, 'q8_0', 5)

    def test_archived_loader_resolution(self):
        text = 'linux-vdso.so.1 (0x1234)\n' + ''.join(
            f'lib{name}.so.0 => {p.LIBS}/lib{name}.so.0 (0x1234)\n'
            for name in ('ggml-cpu', 'ggml', 'ggml-base'))
        mapping = p.linked_libraries(text)
        self.assertEqual(len(mapping), 3)
        for bad in (text + 'libfoo.so => not found\n', text + text.splitlines()[1] + '\n',
                    text.replace(str(p.LIBS / 'libggml-cpu.so.0'), str(p.LIBS / 'libggml-base.so.0'))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                p.linked_libraries(bad)

    def test_only_actual_graph_and_mask_prefixes(self):
        source = (p.HERE / 'tail_gold.cpp').read_text()
        self.assertIn('ggml_flash_attn_ext(ctx, q, k, v, mask, scale, 0, 0)', source)
        self.assertIn('ggml_graph_compute_with_ctx(ctx, graph, 1)', source)
        self.assertIn('for (unsigned visible : {128u, 5u, 33u})', source)
        self.assertNotIn('qbs_ref', source)
        self.assertNotIn('akv_quant', source)
        self.assertIn('original_mask_not_visible128', source)
        self.assertIn('prefix128_capture_tolerance', source)
        self.assertIn('operand_changed', source)

    @unittest.skipUnless(os.environ.get('TAIL_GOLD_RESULT'), 'Set TAIL_GOLD_RESULT after the one actual export')
    def test_completed_functional_gold_artifacts(self):
        path = Path(os.environ['TAIL_GOLD_RESULT']).resolve(strict=True)
        report = json.loads(path.read_text())
        self.assertEqual(report['state'], 'PASS')
        self.assertEqual(report['graphs'], 6)
        self.assertEqual(p.digest(path.parent / 'source-pins.json'), report['source_pins_sha256'])
        p.verify(p.read_json(path.parent / 'source-pins.json'))
        p.verify(report['artifact_sha256'])
        self.assertEqual(p.digest(report['raw_reference_log']), report['raw_reference_log_sha256'])
        self.assertEqual(set(report['outputs']), set(p.KINDS))
        for kind in p.KINDS:
            self.assertEqual(set(report['outputs'][kind]), {'5', '33'})
            for visible in (5, 33):
                row = report['outputs'][kind][str(visible)]
                self.assertEqual(p.output_record(Path(row['path']), kind, visible), row)
            base = report['baseline128'][kind]
            actual = Path(base['path']).read_bytes()
            original = (Path(report['captures'][kind]['directory']) / 'kqv_out-0.bin').read_bytes()
            for (a,), (b,) in zip(struct.iter_unpack('<f', actual), struct.iter_unpack('<f', original)):
                self.assertLessEqual(abs(a-b), 0.004+0.002*abs(b))


if __name__ == '__main__':
    unittest.main()
