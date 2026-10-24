"""Actual GGML tensor definitions; mapping and admission, not model execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from capture_host import validate_capture

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GGML=Path('/home/wangwy/llama/llama.cpp/ggml/include')


class GGMLDecodeTest(unittest.TestCase):
    def check_binary(self,compiler,flags):
        headers={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in GGML.glob('*.h')}
        with tempfile.TemporaryDirectory(prefix='quant-ggml-map-') as tmp:
            binary=Path(tmp)/'test'
            argv=[compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                '-fno-fast-math','-frounding-math',*flags,'-I'+str(ROOT),
                '-I'+str(ROOT/'software/qbs/include'),'-I'+str(GGML),
                HERE/'test_ggml_decode.c',ROOT/'software/qbs/src/qbs_runtime.c','-lm','-o',binary]
            subprocess.run(argv,check=True,timeout=120)
            result=subprocess.run([binary],text=True,capture_output=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout,'GGML_QUANT_MAP_PASS accepted=2048 rejected=23 '
                'deferred=13 output_untouched=1 snan_no_invalid=1\n')
            print(result.stdout,end='')
        self.assertEqual(headers,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in GGML.glob('*.h')})

    def test_real_ggml_metadata(self):
        self.check_binary('/usr/bin/gcc',[])

    def test_sanitized_metadata(self):
        self.check_binary('/usr/bin/clang',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])

    def test_cpp_backend_header(self):
        subprocess.run(['/usr/bin/g++','-std=c++17','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),'-I'+str(GGML),
            '-fsyntax-only','-x','c++','-'],input='#include "software/akv/experimental/quantized_kv/ggml_decode.h"\n',
            text=True,check=True,timeout=120)

    def check_captures(self,compiler,flags):
        capture=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'
        report=json.loads((capture/'result.json').read_text())
        self.assertEqual(report['state'],'REAL_HOST_QUANTIZED_KV_CAPTURED')
        self.assertEqual(hashlib.sha256((capture/'source-pins.json').read_bytes()).hexdigest(),
                         report['source_pins_sha256'])
        with tempfile.TemporaryDirectory(prefix='quant-ggml-capture-') as tmp:
            binary=Path(tmp)/'test'
            subprocess.run([compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                '-fno-fast-math',*flags,'-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),
                '-I'+str(GGML),HERE/'ggml_decode_capture.c',ROOT/'software/qbs/src/qbs_runtime.c',
                '-lm','-o',binary],check=True,timeout=120)
            for q4,kind in enumerate(('q8_0','q4_0')):
                directory=capture/('capture-k-'+kind+'-v-q8_0')
                before=validate_capture(directory,kind)
                self.assertEqual(before,report['captures'][kind])
                data=directory/'decode/block'
                for name,shape,strides in (
                    ('attn_q_input-0',[128,1,12,1],[4,512,512,6144]),
                    ('attn_k_input-0',[128,256,2,1],[18,72,18432,36864] if q4 else [34,136,34816,69632]),
                    ('attn_v_input-0',[128,256,2,1],[34,136,34816,69632]),
                    ('attn_mask_input-0',[256,1,1,1],[2,512,512,512])):
                    meta=json.loads((data/(name+'.json')).read_text())
                    self.assertEqual(meta['shape'],shape)
                    self.assertEqual(meta['strides'],strides)
                result=subprocess.run([binary,str(q4),*[data/(name+'.bin') for name in
                    ('attn_q_input-0','attn_k_input-0','attn_v_input-0','attn_mask_input-0')]],
                    text=True,capture_output=True,check=True,timeout=120)
                self.assertEqual(result.stdout,f'GGML_QUANT_CAPTURE_MAP_PASS q4={q4} '
                    'groups=6 kv_heads=2 d=128 capacity=256 visible=128 output_untouched=1 execution=0\n')
                self.assertEqual(validate_capture(directory,kind),before)
                print(result.stdout,end='')

    def test_real_capture_mapping(self):
        self.check_captures('/usr/bin/gcc',[])

    def test_sanitized_capture_mapping(self):
        self.check_captures('/usr/bin/clang',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])


if __name__=='__main__':
    unittest.main()
