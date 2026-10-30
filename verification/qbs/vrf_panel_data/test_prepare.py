import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

import prepare as p


class PanelDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='qbs-panel-host-')
        cls.root = Path(cls.temp.name)
        cls.out = cls.root / 'good'
        cls.manifest = p.prepare(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_full_oracle_and_pins(self):
        report = p.verify_artifacts(self.out, p.CAPTURE)
        self.assertEqual(report['outputs'], 256)
        self.assertEqual(report['llama_mismatches'], 0)
        p.check_pins(self.manifest['inputs'])
        for name, record in self.manifest['artifacts'].items():
            self.assertEqual(p.sha(self.out / name), record['sha256'])
            self.assertEqual((self.out / name).stat().st_size, record['bytes'])
        status = json.loads((self.out / 'status.json').read_text())
        self.assertEqual(status['manifest_sha256'], p.sha(self.out / 'manifest.json'))

    def test_global_output_stride(self):
        raw = b''.join(struct.pack('<I', i) for i in range(1536 * 15))
        crop = struct.unpack('<256I', p.crop_llama(raw))
        self.assertEqual(list(crop), [r*1536+c for r in range(4) for c in range(64)])
        with self.assertRaises(ValueError):
            p.crop_llama(raw[:-1])

    def test_stripe_offsets_and_last_k3(self):
        records = p.stripe_records()
        self.assertEqual([s['k_blocks'] for s in records], [4]*8+[3])
        self.assertEqual(records[-1]['activation_offset'], 32*1168)
        self.assertEqual(records[-1]['weight_offsets'][1] + records[-1]['weight_bytes_per_panel'], 470400)
        self.assertTrue(all(s['activation_bytes'] <= 4672 for s in records))

    def test_accepted_activation_and_full_panel_bits(self):
        text = (p.ACCEPTED / 'q6_K_m4a/input.vectors').read_text()
        activation, outputs = p.accepted_data(text)
        self.assertEqual(activation, (self.out / 'activation_q8k_m4.bin').read_bytes())
        self.assertEqual(outputs, (self.out / 'expected_panel_f32.bin').read_bytes()[:512])
        line = next(line for line in text.splitlines() if line.startswith('A '))
        for bad in (text.replace(line+'\n', '', 1), text.replace(line, line+'\n'+line, 1),
                    text.replace('4 32 35 01', '4 32 34 01', 1),
                    text.replace('A 0 0 ffff', 'A 0 0 fffe', 1)):
            with self.assertRaises(ValueError):
                p.accepted_data(bad)

    def mutate(self, name, data):
        out = self.root / 'mutant'
        if out.exists():
            shutil.rmtree(out)
        out.mkdir()
        for item in self.out.iterdir():
            if item.suffix in ('.bin', '.json'):
                shutil.copyfile(item, out / item.name)
        (out / name).write_bytes(data)
        with self.assertRaises(ValueError):
            p.verify_artifacts(out, p.CAPTURE)

    def test_bad_weight_stride_and_missing_tail(self):
        data = bytearray((self.out / 'weight_striped_r4.bin').read_bytes())
        data[64*4*210+500] ^= 1
        self.mutate('weight_striped_r4.bin', data)
        self.mutate('weight_full_r4.bin', (self.out / 'weight_full_r4.bin').read_bytes()[:-210])

    def test_activation_aux_and_output_order_mutations(self):
        data = bytearray((self.out / 'activation_q8k_m4.bin').read_bytes())
        data[1040+2*4] ^= 1
        self.mutate('activation_q8k_m4.bin', data)
        self.mutate('llama_f32.bin', (p.CAPTURE / p.OP / 'output_f32.bin').read_bytes()[:1024])
        self.mutate('expected_f32.bin', (self.out / 'expected_panel_f32.bin').read_bytes())

    def test_fake_oracle_pass_and_flags(self):
        good = json.loads((self.out / 'oracle.json').read_text())
        for key, bad in [('state', 'PASS_BOGUS'), ('outputs', 128), ('fflags', 32),
                         ('panel_fflags', [0, 0]), ('llama_mismatches', 1), ('max_abs', 123)]:
            record = copy.deepcopy(good)
            record[key] = bad
            self.mutate('oracle.json', json.dumps(record).encode())

    def test_capture_and_source_pin_rejection(self):
        path = self.root / 'pin.bin'
        path.write_bytes(b'original')
        pins = {str(path): p.sha(path)}
        path.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            p.check_pins(pins)
        with self.assertRaises(FileNotFoundError):
            p.validate_capture(self.root)

    def test_host_reproducible_generator_outputs(self):
        out = self.root / 'repeat'
        out.mkdir()
        for name in ('weight_row.bin', 'activation_f32.bin', 'llama_f32.bin'):
            shutil.copyfile(self.out / name, out / name)
        subprocess.run([self.out / 'generate', out], check=True, capture_output=True, timeout=120, env=p.ENV)
        for item in out.iterdir():
            self.assertEqual(item.read_bytes(), (self.out / item.name).read_bytes(), item.name)

    def test_gnu_binary_rebuild_reproducible(self):
        binary = self.root / 'rebuilt-generator'
        subprocess.run(['/usr/bin/gcc', *p.FLAGS, '-static', '-Wl,--build-id=none',
                        p.HERE / 'generate.c', p.HERE.parent / 'qbs_ref.c', '-lm', '-o', binary],
                       cwd=p.ROOT, check=True, capture_output=True, timeout=120, env=p.ENV)
        self.assertEqual(p.sha(binary), p.sha(self.out / 'generate'))

    def test_generator_rejects_short_input(self):
        out = self.root / 'short'
        out.mkdir()
        (out / 'weight_row.bin').write_bytes(b'not a complete weight matrix')
        result = subprocess.run([self.out / 'generate', out], capture_output=True, text=True,
                                timeout=30, env=p.ENV)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PANEL_DATA_FAIL input length', result.stderr)
        self.assertNotIn('PANEL_DATA_PASS', result.stdout)

    def test_generated_header_and_blob_assembly_compile(self):
        subprocess.run(['/usr/bin/gcc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsyntax-only', '-x', 'c', '-include', self.out / 'panel_data.h', '/dev/null'],
                       check=True, capture_output=True, timeout=60, env=p.ENV)
        subprocess.run(['/usr/bin/gcc', '-c', self.out / 'panel_data.S', '-o', self.root / 'panel_data.o'],
                       check=True, capture_output=True, timeout=60, env=p.ENV)


if __name__ == '__main__':
    unittest.main()
