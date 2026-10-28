"""Host admission only: exact sealed-source delta, rejection parity, real bytes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'software/akv/experimental/quantized_kv/selection.h'
SUCCESSOR = SOURCE.with_name('selection_strided.h')
SOURCE_SHA256 = 'd597ccdf8da49a14f029626825bdceb939af2029665216cd47a07c1acf00cff7'
CAPTURE = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StridedSelectionTest(unittest.TestCase):
    def test_exact_sealed_body_delta(self):
        self.assertEqual(sha(SOURCE), SOURCE_SHA256)
        source = SOURCE.read_text()
        original = source[source.index('static inline int akv_quant_select('):source.rindex('\n#endif')].rstrip()
        self.assertEqual(original.count('p->key.token_stride != key_row'), 1)
        expected = original.replace('akv_quant_select(', 'akv_quant_select_strided(', 1).replace(
            'p->key.token_stride != key_row', 'p->key.token_stride < key_row', 1)
        expected = expected.replace(
            'AKV_QUANT_FIELD_COPY(&bits, (const unsigned char *)p->query.data + head * p->query.head_stride +\n'
            '                          (block * 32u + d) * 4u, 4);',
            'AKV_QUANT_FIELD_COPY(&bits, AKV_QUANT_PROVEN_ALIGNMENT((const unsigned char *)p->query.data + head * p->query.head_stride +\n'
            '                          (block * 32u + d) * 4u,4), 4);',1).replace(
            'AKV_QUANT_FIELD_COPY(&bits, (const unsigned char *)view->data + head * view->head_stride +\n'
            '                           token * view->token_stride + block * block_bytes, 2);',
            'AKV_QUANT_FIELD_COPY(&bits, AKV_QUANT_PROVEN_ALIGNMENT((const unsigned char *)view->data + head * view->head_stride +\n'
            '                           token * view->token_stride + block * block_bytes,2), 2);',1)
        expected = expected.replace(
            '        if ((bits & UINT32_C(0x7f800000)) == UINT32_C(0x7f800000)) return AKV_QUANT_SELECT_NONFINITE;\n','',1).replace(
            '      /* Conservative source-domain guard',
            '      /* The maximum absolute bit pattern is nonfinite iff any element is. */\n'
            '      if (maximum >= UINT32_C(0x7f800000)) return AKV_QUANT_SELECT_NONFINITE;\n'
            '      /* Conservative source-domain guard',1)
        successor = SUCCESSOR.read_text()
        self.assertIn('"' + SOURCE_SHA256 + '"', successor)
        self.assertIn('#include "selection.h"', successor)
        actual = successor[successor.index('static inline int akv_quant_select_strided('):successor.rindex('\n#undef AKV_QUANT_PROVEN_ALIGNMENT')].rstrip()
        self.assertEqual(actual, expected)

    def compile(self, source, binary, sanitized=False):
        compiler = '/usr/bin/clang' if sanitized else shutil.which('gcc')
        flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if sanitized else []
        subprocess.run([compiler, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-fno-fast-math', '-frounding-math', *flags,
                        '-I' + str(ROOT), '-I' + str(ROOT / 'software/qbs/include'), source,
                        ROOT / 'software/qbs/src/qbs_runtime.c', '-lm', '-o', binary],
                       check=True, timeout=120, capture_output=True, text=True)

    def execute(self, binary, *args):
        result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        print(result.stdout, end='')
        return result.stdout

    def test_existing_rejection_suite_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='akv-strided-legacy-') as tmp:
            original, successor = Path(tmp) / 'original', Path(tmp) / 'successor'
            self.compile(HERE.parent / 'test_selection.c', original)
            self.compile(HERE / 'legacy.c', successor)
            self.assertEqual(self.execute(original), self.execute(successor))

    def test_focused_layouts_and_rejections(self):
        with tempfile.TemporaryDirectory(prefix='akv-strided-selection-') as tmp:
            binary = Path(tmp) / 'test'
            self.compile(HERE / 'test_selection.c', binary)
            self.assertRegex(self.execute(binary), r'^STRIDED_SELECTION_HOST_PASS accepted=\d+ rejected=\d+ real_derived=0 output_untouched=1 native_execution=0\n$')

    def test_sanitized_layouts_and_rejections(self):
        with tempfile.TemporaryDirectory(prefix='akv-strided-sanitized-') as tmp:
            binary = Path(tmp) / 'test'
            self.compile(HERE / 'test_selection.c', binary, sanitized=True)
            self.assertRegex(self.execute(binary), r'^STRIDED_SELECTION_HOST_PASS accepted=\d+ rejected=\d+ real_derived=0 output_untouched=1 native_execution=0\n$')

    def test_cpp_header(self):
        subprocess.run([shutil.which('g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-I' + str(ROOT), '-I' + str(ROOT / 'software/qbs/include'),
                        '-fsyntax-only', '-x', 'c++', '-'],
                       input='#include "software/akv/experimental/quantized_kv/selection_strided.h"\n',
                       text=True, check=True, capture_output=True, timeout=120)

    def test_real_capture_coordinate_repack(self):
        report = json.loads((CAPTURE / 'result.json').read_text())
        self.assertEqual(report['state'], 'REAL_HOST_QUANTIZED_KV_CAPTURED')
        self.assertEqual(sha(CAPTURE / 'source-pins.json'), report['source_pins_sha256'])
        with tempfile.TemporaryDirectory(prefix='akv-strided-real-') as tmp:
            tmp = Path(tmp)
            binary = tmp / 'test'
            self.compile(HERE / 'test_selection.c', binary, sanitized=True)
            for q4, kind in enumerate(('q8_0', 'q4_0')):
                receipt = report['captures'][kind]
                self.assertEqual(receipt['state'], 'REAL_HOST_CAPTURE_LAYOUT_CHECKED')
                data = CAPTURE / ('capture-k-' + kind + '-v-q8_0') / 'decode/block'
                pins = receipt['file_sha256']
                for path, expected in pins.items():
                    self.assertEqual(sha(Path(path)), expected)
                masks = (data / 'attn_mask_input-0.bin').read_bytes()
                self.assertEqual(masks, bytes(256) + b'\x00\xfc' * 128)
                paths = []
                for label, row, shape in (
                    ('q', 512, [128, 1, 12, 1]),
                    ('k', 72 if q4 else 136, [128, 256, 2, 1]),
                    ('v', 136, [128, 256, 2, 1]),
                ):
                    name = 'attn_' + label + '_input-0'
                    metadata = json.loads((data / (name + '.json')).read_text())
                    self.assertEqual(metadata['shape'], shape)
                    strides = metadata['strides']
                    self.assertEqual(strides, [4, 512, 512, 6144] if label == 'q' else
                                     [row // 4, row, row * 256, row * 512])
                    raw = (data / (name + '.bin')).read_bytes()
                    self.assertEqual(len(raw), strides[3])
                    # Crop the genuine visible prefix offline, never synthesize
                    # new operand values. C also checks every token-major row.
                    cropped = b''.join(raw[h * strides[2] + t * strides[1]:
                                           h * strides[2] + t * strides[1] + row]
                                       for h in range(shape[2])
                                       for t in range(1 if label == 'q' else 128))
                    self.assertEqual(len(cropped), row * shape[2] * (1 if label == 'q' else 128))
                    for h in range(shape[2]):
                        for t in range(1 if label == 'q' else 128):
                            n = h * (1 if label == 'q' else 128) + t
                            self.assertEqual(cropped[n * row:(n + 1) * row],
                                             raw[h * strides[2] + t * strides[1]:h * strides[2] + t * strides[1] + row])
                    target = tmp / (kind + '-' + label + '.bin')
                    target.write_bytes(cropped)
                    paths.append(target)
                self.assertEqual(self.execute(binary, str(q4), *paths),
                                 'STRIDED_SELECTION_HOST_PASS accepted=50 rejected=30 real_derived=1 output_untouched=1 native_execution=0\n')
                for path, expected in pins.items():
                    self.assertEqual(sha(Path(path)), expected)


if __name__ == '__main__':
    unittest.main()
