#!/usr/bin/env python3
"""Check pure admission against both frozen original model captures on host."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from capture_host import validate_capture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CAPTURE = ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'


class RealCaptureSelectionTest(unittest.TestCase):
    def test_two_original_captures(self):
        report = json.loads((CAPTURE/'result.json').read_text())
        self.assertEqual(report['state'], 'REAL_HOST_QUANTIZED_KV_CAPTURED')
        self.assertEqual(hashlib.sha256((CAPTURE/'source-pins.json').read_bytes()).hexdigest(),
                         report['source_pins_sha256'])
        with tempfile.TemporaryDirectory(prefix='quant-selection-capture-') as tmp:
            binary = Path(tmp)/'test'
            subprocess.run([shutil.which('gcc'), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-I'+str(ROOT), '-I'+str(ROOT/'software/qbs/include'),
                HERE/'selection_capture.c', ROOT/'software/qbs/src/qbs_runtime.c', '-lm', '-o', binary],
                check=True, timeout=120)
            for kind, name in enumerate(('q8_0', 'q4_0')):
                directory = CAPTURE/('capture-k-'+name+'-v-q8_0')
                before = validate_capture(directory, name)
                self.assertEqual(before, report['captures'][name])
                data = directory/'decode/block'
                for file, shape, strides in (
                    ('attn_q_input-0', [128,1,12,1], [4,512,512,6144]),
                    ('attn_v_input-0', [128,256,2,1], [34,136,34816,69632])):
                    metadata = json.loads((data/(file+'.json')).read_text())
                    self.assertEqual(metadata['shape'], shape)
                    self.assertEqual(metadata['strides'], strides)
                result = subprocess.run([binary, str(kind), *[data/(file+'.bin') for file in
                    ('attn_q_input-0', 'attn_k_input-0', 'attn_v_input-0', 'attn_mask_input-0')]],
                    check=True, capture_output=True, text=True, timeout=120)
                self.assertEqual(result.stdout, f'QUANT_CAPTURE_SELECTION_HOST_PASS q4={kind} '
                    'groups=6 kv_heads=2 d=128 visible=128 outputs_untouched=1 device=reference native_execution=0\n')
                self.assertEqual(validate_capture(directory, name), before)
                print(result.stdout, end='')


if __name__ == '__main__':
    unittest.main()
