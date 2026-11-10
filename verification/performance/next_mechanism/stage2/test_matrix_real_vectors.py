#!/usr/bin/env python3
"""Host checks for prepared raw-data oracle; no GGML output is synthesized."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import run_matrix_qwen3 as q

PREPARED = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None


class OracleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PREPARED is None:
            raise ValueError('Pass the prepared output directory')
        cls.old = q.checker.legacy()
        cls.config = json.loads((PREPARED / 'selection.json').read_text())
        cls.program = cls.config['oracle']

    def test_original_four_vectors_byte_exact(self):
        for name, *_ in self.old.SLICES:
            self.assertEqual((PREPARED / 'prior_validation' / f'{name}.txt').read_bytes(),
                             (q.checker.ORIGINAL / f'{name}_baseline.txt').read_bytes())

    def test_both_projection_output_maps(self):
        for view in ('attn_q', 'ffn_gate'):
            result = q.pair_maps(self.old, self.config['vectors'][view])
            self.assertEqual(result['outputs'], 256)
            self.assertTrue(result['bit_exact'])

    def test_complete_k_and_exact_shapes(self):
        for files in self.config['vectors'].values():
            for name, start, m, col, n in self.old.SLICES:
                c, = self.old.vectors(Path(files[name]['baseline']).read_text())
                self.assertEqual((c['profile'], c['m'], c['n'], c['kb']), (1, m, n, 8))
                self.assertEqual(c['counts'][3], m * n * 2048)
                self.assertEqual(len(c['outputs']), 128)

    def test_no_ggml_golden_claim_or_file(self):
        self.assertIsNone(self.config['captured_golden'])
        self.assertFalse(self.config['ggml_projection_check'])
        self.assertEqual(self.config['golden'], 'qbs_ref')
        for view in ('attn_q', 'ffn_gate'):
            self.assertFalse((PREPARED / 'inputs/capture' / view / 'output_f32.bin').exists())
            for name, *_ in self.old.SLICES:
                text = (PREPARED / view / f'{name}_oracle.log').read_text()
                self.assertIn('golden=qbs_ref captured_golden=none ggml_projection_check=0', text)

    def test_real_input_shapes_hashes_and_eight_rows(self):
        for view in ('attn_q', 'ffn_gate'):
            folder = PREPARED / 'inputs/capture' / view
            meta = json.loads((folder / 'operator.json').read_text())
            weight, activation = folder / 'weight_q4_K.bin', folder / 'activation_f32.bin'
            self.assertEqual(weight.stat().st_size, 128 * 8 * 144)
            data = activation.read_bytes()
            self.assertEqual(len(data), 8 * 2048 * 4)
            self.assertEqual(len({data[r*8192:(r+1)*8192] for r in range(8)}), 8)
            self.assertEqual(q.checker.sha(weight), meta['weight_sha256'])
            self.assertEqual(q.checker.sha(activation), meta['activation_sha256'])

    def test_only_dot_expectation_changes(self):
        for files in self.config['vectors'].values():
            for name, *_ in self.old.SLICES:
                before = Path(files[name]['baseline']).read_text()
                expected, changes = self.old.candidate_vector(before)
                self.assertEqual(Path(files[name]['candidate']).read_text(), expected)
                self.assertEqual(len(changes), int(name.startswith('m8')))

    def test_bad_geometry_rejected(self):
        capture = PREPARED / 'inputs/capture/attn_q'
        with tempfile.TemporaryDirectory() as folder:
            for args in ((128, 2048, 1, 8, 0, 16), (128, 2048, 0, 8, 0, 17),
                         (128, 2047, 0, 4, 0, 32), (128, 2048, 0, 3, 0, 32)):
                path = Path(folder) / 'vector'
                result = subprocess.run([self.program, str(path), str(capture), *map(str, args)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(path.exists())

    def test_truncated_capture_has_no_synthetic_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'weight_q4_K.bin').write_bytes(b'\x00' * 143)
            (root / 'activation_f32.bin').write_bytes(b'\x00' * 65536)
            result = subprocess.run([self.program, str(root / 'vector'), str(root), '128', '2048', '0', '4', '0', '32'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'vector').exists())

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'vector'
            path.write_bytes(b'KEEP')
            result = subprocess.run([self.program, str(path), str(PREPARED / 'inputs/capture/attn_q'),
                                     '128', '2048', '0', '4', '0', '32'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), b'KEEP')


if __name__ == '__main__':
    unittest.main(verbosity=2)
