"""Prefill mapping/admission with real GGML allocations and sealed libraries."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
CAPTURE=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'
GGML=Path('/home/wangwy/llama/llama-q4km-extract/ggml/include')


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class MemoryTest(unittest.TestCase):
    def run_compilers(self, cc, cxx, flags):
        receipt=json.loads((CAPTURE/'result.json').read_text())
        self.assertEqual(digest(CAPTURE/'build-artifacts.json'),receipt['build_artifacts_sha256'])
        self.assertEqual(digest(CAPTURE/'source-pins.json'),receipt['source_pins_sha256'])
        pins=json.loads((CAPTURE/'build-artifacts.json').read_text())
        source_pins=json.loads((CAPTURE/'source-pins.json').read_text())
        for p in GGML.glob('*.h'):
            self.assertEqual(digest(p),source_pins[str(p)])
            pins[str(p)]=digest(p)
        for p,h in pins.items(): self.assertEqual(digest(p),h)
        libs=CAPTURE/'build/bin'
        with tempfile.TemporaryDirectory(prefix='prefill-real-memory-') as tmp:
            binary=Path(tmp)/'test'; runtime=Path(tmp)/'runtime.o'
            inc=['-I'+str(ROOT),'-I'+str(GGML),'-I'+str(ROOT/'software/qbs/include')]
            subprocess.run([cc,'-std=gnu11','-O2',*flags,*inc,'-c',
                            ROOT/'software/qbs/src/qbs_runtime.c','-o',runtime],check=True,timeout=120)
            subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror',*flags,*inc,
                            HERE/'test_ggml_prefill_memory.cpp',runtime,'-L'+str(libs),
                            '-Wl,-rpath,'+str(libs),'-lggml-cpu','-lggml','-lggml-base',
                            '-pthread','-lm','-o',binary],check=True,timeout=120)
            run=subprocess.run([binary],capture_output=True,text=True,timeout=60,
                               env=dict(os.environ,LD_LIBRARY_PATH=str(libs)))
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertEqual(run.stdout,'PREFILL_REAL_MEMORY_PASS accepted=54 rejected=162 '
                             'actual_allocator=1 nonzero_views=1 execution=0\n')
        for p,h in pins.items(): self.assertEqual(digest(p),h)

    def test_gcc(self): self.run_compilers('/usr/bin/gcc','/usr/bin/g++',[])
    def test_ubsan(self):
        self.run_compilers('/usr/bin/clang','/usr/bin/clang++',
                           ['-fsanitize=undefined','-fno-sanitize-recover=undefined'])


if __name__=='__main__': unittest.main()
