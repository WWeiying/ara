"""Use sealed real GGML libraries and their byte-identical public headers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CAPTURE=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'
GGML=Path('/home/wangwy/llama/llama.cpp/ggml/include')
ORIGINAL=Path('/home/wangwy/llama/llama-q4km-extract/ggml/include')


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


class GGMLMemoryTest(unittest.TestCase):
    def check_binary(self,cc,cxx,flags):
        report=json.loads((CAPTURE/'result.json').read_text())
        manifest=CAPTURE/'build-artifacts.json'
        self.assertEqual(digest(manifest),report['build_artifacts_sha256'])
        pins=json.loads(manifest.read_text())
        original_pins=json.loads((CAPTURE/'source-pins.json').read_text())
        self.assertEqual(digest(CAPTURE/'source-pins.json'),report['source_pins_sha256'])
        for name in ('ggml.h','ggml-backend.h','ggml-cpu.h','ggml-alloc.h'):
            self.assertEqual(digest(ORIGINAL/name),original_pins[str(ORIGINAL/name)])
            self.assertEqual((GGML/name).read_bytes(),(ORIGINAL/name).read_bytes())
            pins[str(GGML/name)]=digest(GGML/name)
            pins[str(ORIGINAL/name)]=digest(ORIGINAL/name)
        for path,sha in pins.items(): self.assertEqual(digest(Path(path)),sha)
        libs=CAPTURE/'build/bin'
        with tempfile.TemporaryDirectory(prefix='ggml-real-memory-') as tmp:
            runtime=Path(tmp)/'runtime.o'; binary=Path(tmp)/'test'
            includes=['-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),'-I'+str(GGML)]
            subprocess.run([cc,'-std=gnu11','-O2',*flags,*includes,'-c',
                ROOT/'software/qbs/src/qbs_runtime.c','-o',runtime],check=True,timeout=120)
            subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror',*flags,*includes,
                HERE/'test_ggml_memory.cpp',runtime,'-L'+str(libs),'-Wl,-rpath,'+str(libs),
                '-lggml-cpu','-lggml','-lggml-base','-pthread','-lm','-o',binary],check=True,timeout=120)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=120,
                env=dict(os.environ,LD_LIBRARY_PATH=str(libs)))
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout,'GGML_REAL_MEMORY_PASS accepted=96 rejected=672 '
                'actual_allocator=1 nonzero_view=1 same_buffer=1 output_untouched=1 execution=0\n')
            print(result.stdout,end='')
        for path,sha in pins.items(): self.assertEqual(digest(Path(path)),sha)

    def test_actual_backend_allocations(self):
        self.check_binary('/usr/bin/gcc','/usr/bin/g++',[])

    def test_sanitized_backend_allocations(self):
        self.check_binary('/usr/bin/clang','/usr/bin/clang++',
            ['-fsanitize=address,undefined','-fno-omit-frame-pointer'])


if __name__=='__main__': unittest.main()
