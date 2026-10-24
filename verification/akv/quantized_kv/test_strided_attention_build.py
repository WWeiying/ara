"""Host build-contract tests only; no simulation or cross compilation."""
import copy
from pathlib import Path
import unittest

import build_strided_attention as b


def metadata(kind):
    block = 18 if kind == 'q4_0' else 34
    row = 4 * block
    return dict(type=kind, shape=[128, 256, 2, 1], strides=[block, row, 256*row, 512*row], nbytes=512*row)


def fair():
    return dict(rvv_value_decode=True, rvv_baseline_decode=True,
                ordinary_value_decode='same RVV decoder as candidate',
                scope='Public-entry ABBA; both schedules use identical RVV V decoder')


def disassembly():
    required = ('akv_quant_strided_execute', 'quantize_row_q8_0', 'ggml_vec_dot_q4_0_q8_0',
                'ggml_vec_dot_q8_0_q8_0', 'quant_kv_ggml_mad_f32', 'quant_kv_ggml_scale_f32',
                'qbs_native_execute_command')
    return ('0000 <strided_value_decode>:\n vle8.v\n vsext.vf4\n vfcvt.f.x.v\n vfmul.vf\n vse32.v\n\n'
            '0010 <main>:\n vsetivli zero,1,e32,m1,ta,ma\n vmv.v.i v8,0\n vmv.x.s zero,v8\n\n' +
            ''.join('0020 <' + name + '>:\n ret\n\n' for name in required))


class StridedAttentionBuildTest(unittest.TestCase):
    def test_full_two_head_coordinate_permutation(self):
        for kind in ('q8_0', 'q4_0'):
            meta = metadata(kind)
            row = meta['strides'][1]
            # Each row and byte coordinate is distinguishable, including the
            # invisible half of capacity and the second KV head.
            raw = bytes((h*97 + t*13 + t//16 + j*7) % 256
                        for h in range(2) for t in range(256) for j in range(row))
            saved = copy.deepcopy(meta)
            physical = b.interleave(meta, raw, kind)
            self.assertEqual(meta, saved)
            self.assertEqual(len(physical), len(raw))
            self.assertNotEqual(physical, raw)
            reconstructed = b''.join(physical[t*2*row+h*row:t*2*row+(h+1)*row]
                                     for h in range(2) for t in range(256))
            self.assertEqual(reconstructed, raw)

    def test_malformed_or_already_interleaved_metadata_rejected(self):
        for kind in ('q8_0', 'q4_0'):
            good = metadata(kind)
            raw = bytes(good['nbytes'])
            for key, bad in (('type', 'f16'), ('shape', [128, 128, 2, 1]),
                             ('shape', [128, 256, 1, 1]), ('nbytes', len(raw)-1),
                             ('strides', [good['strides'][0], 2*good['strides'][1], good['strides'][1], len(raw)])):
                with self.subTest(kind=kind, key=key, bad=bad), self.assertRaises(ValueError):
                    b.interleave(dict(good, **{key: bad}), raw, kind)
            for bad_raw in (raw[:-1], raw+b'\0'):
                with self.assertRaises(ValueError):
                    b.interleave(good, bad_raw, kind)
        with self.assertRaises(ValueError):
            b.interleave(metadata('q8_0'), bytes(69632), 'q5_0')

    def test_requires_matched_rvv_predecessor(self):
        b.require_fair(fair())
        for key, wrong in (('rvv_value_decode', False), ('rvv_value_decode', 1),
                           ('rvv_baseline_decode', False), ('rvv_baseline_decode', 1),
                           ('ordinary_value_decode', 'unchanged production scalar decoder'),
                           ('scope', 'hardware-only speedup')):
            with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError):
                b.require_fair(dict(fair(), **{key: wrong}))
        for key in fair():
            report = fair()
            del report[key]
            with self.assertRaises(ValueError):
                b.require_fair(report)

    def test_original_compile_link_contract(self):
        base = Path('/unused/predecessor')
        source = str(b.HERE / 'attention_rvv_baseline_main.c')
        compile_command = ['/tool/riscv64-unknown-elf-gcc', '-c', source, '-o', str(base / 'main.o'),
                           '-ffp-contract=fast', '-fno-fast-math', '-ffunction-sections', '-fdata-sections',
                           '-march=rv64gcv_zfh_zvfh', '-Werror']
        link = ['cc', '-nostdlib', str(base / 'main.o'), '-Wl,--gc-sections', '-Wl,-Map=/old/link.map', '-o', '/old/test.elf']
        records = [dict(argv=compile_command), dict(argv=link)]
        self.assertEqual(b.command_templates(records, base), (compile_command, link))
        for old, new in (('-ffp-contract=fast', '-ffp-contract=off'),
                         ('-fno-fast-math', '-ffast-math'), ('-Werror', '-w')):
            changed = [new if x == old else x for x in compile_command]
            with self.assertRaises(ValueError):
                b.command_templates([dict(argv=changed), dict(argv=link)], base)
        with self.assertRaises(ValueError):
            b.command_templates(records + [records[0]], base)
        with self.assertRaises(ValueError):
            b.command_templates([records[0], dict(argv=link+[str(base/'main.o')])], base)

    def test_disassembly_requires_real_rvv_and_defined_drain(self):
        text = disassembly()
        b.verify_disassembly(text)
        for operation in ('vle8.v', 'vsext.vf4', 'vfcvt.f.x.v', 'vfmul.vf', 'vse32.v',
                          'vsetivli zero,1,e32,m1', 'vmv.v.i v8,0', 'vmv.x.s zero,v8',
                          'akv_quant_strided_execute'):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                b.verify_disassembly(text.replace(operation, 'missing'))
        for old in ('qbs_ref_execute', 'archived_main', 'archived_main.constprop.0',
                    'dequantize_row_q8_0', 'fair_value_decode'):
            with self.subTest(old=old), self.assertRaises(ValueError):
                b.verify_disassembly(text + '\n0000 <' + old + '>:\n ret\n')

    def test_actual_capture_full_rows_and_pins(self):
        for kind in ('q8_0', 'q4_0'):
            pins = {}
            payloads, sources = b.capture_payloads(kind, pins)
            for label, row in (('key', 72 if kind == 'q4_0' else 136), ('value', 136)):
                path = Path(sources[label]['path'])
                self.assertEqual(pins[str(path)], b.s.digest(path))
                raw = path.read_bytes()
                self.assertEqual(len(payloads[label]), 512*row)
                for h in range(2):
                    for t in range(256):
                        self.assertEqual(payloads[label][(t*2+h)*row:(t*2+h+1)*row],
                                         raw[(h*256+t)*row:(h*256+t+1)*row])
            # An existing provenance mismatch must not be overwritten.
            with self.assertRaises(ValueError):
                b.capture_payloads(kind, {sources['key']['path']: '0'*64})

    def test_live_main_timing_and_fair_decoder_contract(self):
        text = b.MAIN.read_text()
        self.assertIn('#define main archived_main\n#include "attention_main.c"', text)
        self.assertIn('__attribute__((noinline)) void strided_value_decode', text)
        self.assertIn('strided_value_decode(attention_strided_value + token * 272u', text)
        self.assertIn('bindings={quantize_row_q8_0, strided_value_decode,', text)
        self.assertIn('attention_strided_key + first_token * 2u * row', text)
        begin = text.index('const uint64_t start = strided_cycles();')
        end = text.index('const uint64_t elapsed = strided_cycles()-start;')
        window = text[begin:end]
        self.assertLess(window.index('akv_quant_ggml_map('), window.index('akv_quant_strided_execute('))
        self.assertIn('quantize_row_q8_0(attention_query+head*DIM', window)
        self.assertIn('akv_quant_online_head_major(', window)
        self.assertTrue(window.rstrip().endswith('drain();'))
        self.assertIn('fc!=baseline_fcsr', text[end:])
        self.assertIn('report.key_panels!=4 || report.key_bytes!=TOKENS*key_row', text[end:])
        self.assertIn('const unsigned order[]={0,1,1,0};', text)
        self.assertNotIn('QUANT_COMMON_', text)


if __name__ == '__main__':
    unittest.main()
