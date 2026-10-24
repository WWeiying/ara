"""Actual GGML graph arithmetic vs the common entry with a host QBS executor."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

from capture_host import validate_capture

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CAPTURE=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'
SOURCE=Path('/home/wangwy/llama/llama-q4km-extract')
GGML=Path('/home/wangwy/llama/llama.cpp/ggml/include')


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


class GGMLGraphTest(unittest.TestCase):
    def check_graph(self,cc,cxx,sanitizer):
        report=json.loads((CAPTURE/'result.json').read_text())
        self.assertEqual(digest(CAPTURE/'source-pins.json'),report['source_pins_sha256'])
        original=json.loads((CAPTURE/'source-pins.json').read_text())
        self.assertEqual(digest(CAPTURE/'build-artifacts.json'),report['build_artifacts_sha256'])
        pins=json.loads((CAPTURE/'build-artifacts.json').read_text())
        for name in ('ggml.h','ggml-backend.h','ggml-cpu.h','ggml-alloc.h'):
            old=SOURCE/'ggml/include'/name
            self.assertEqual(digest(old),original[str(old)])
            self.assertEqual(old.read_bytes(),(GGML/name).read_bytes())
            pins[str(old)]=digest(old); pins[str(GGML/name)]=digest(GGML/name)
        for path,sha in pins.items(): self.assertEqual(digest(Path(path)),sha)
        commands=json.loads((CAPTURE/'build/compile_commands.json').read_text())
        production=next(r for r in commands if r['file'].endswith('/ggml-cpu/ggml-cpu.c'))
        base=list(production.get('arguments') or shlex.split(production['command']))
        with tempfile.TemporaryDirectory(prefix='ggml-quant-graph-') as tmp:
            tmp=Path(tmp); objects=[]
            includes=['-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),'-I'+str(GGML)]
            for source,name,contract in ((ROOT/'software/akv/experimental/quantized_kv/runtime.c','runtime','fast'),
                                         (ROOT/'software/qbs/src/qbs_runtime.c','qbs_runtime','off'),
                                         (ROOT/'verification/qbs/qbs_ref.c','reference','off')):
                obj=tmp/(name+'.o'); objects.append(obj)
                subprocess.run([cc,'-std=gnu11','-O2','-fno-fast-math','-ffp-contract='+contract,
                    *sanitizer,*includes,'-c',source,'-o',obj],check=True,timeout=120)
            # Compile only the thin calls into the exact original vec.h with
            # the captured CPU target flags; no copied/synthetic PV arithmetic.
            command=list(base); command[0]=cc
            command[command.index(production['file'])]=str(HERE/'pv_primitives.c')
            command[command.index('-o')+1]=str(tmp/'pv.o')
            command.extend(sanitizer)
            dep=[x for i,x in enumerate(command) if i not in
                 (command.index('-c'),command.index('-o'),command.index('-o')+1)]+['-M','-MT','object']
            deps=subprocess.run(dep,cwd=production['directory'],text=True,capture_output=True,check=True,timeout=120)
            for name in shlex.split(deps.stdout.replace('\\\n',' ').split(':',1)[1]):
                path=Path(name).resolve()
                if path.is_relative_to(SOURCE):
                    self.assertEqual(digest(path),original[str(path)])
                    pins[str(path)]=digest(path)
            subprocess.run(command,cwd=production['directory'],check=True,timeout=120)
            objects.append(tmp/'pv.o')
            libs=CAPTURE/'build/bin'; binary=tmp/'test'
            subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror',*sanitizer,*includes,
                HERE/'test_ggml_graph.cpp',*objects,'-L'+str(libs),'-Wl,-rpath,'+str(libs),
                '-lggml-cpu','-lggml','-lggml-base','-pthread','-lm','-o',binary],check=True,timeout=120)
            for kind in ('q8_0','q4_0'):
                capture=CAPTURE/('capture-k-'+kind+'-v-q8_0')
                self.assertEqual(validate_capture(capture,kind),report['captures'][kind])
                result=subprocess.run([binary,kind,capture/'decode/block'],text=True,capture_output=True,
                    timeout=120,env=dict(os.environ,LD_LIBRARY_PATH=str(libs)))
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                pattern=(r'GGML_QUANT_GRAPH_PASS kind='+kind+r' heads=12 kv_heads=2 d=128 visible=128 '
                    r'outputs=1536 repeats=2 commands_per_call=16 decodes_per_call=256 '
                    r'fallback_before_work=1 ordinary_fallback_graph=1 failure_no_retry=1 inputs_unchanged=1 ordinary_gold_max=([0-9.e+-]+) '
                    r'candidate_gold_max=([0-9.e+-]+) candidate_ordinary_max=([0-9.e+-]+) '
                    r'executor=qbs_ref performance=not_measured\n')
                match=re.fullmatch(pattern,result.stdout)
                self.assertIsNotNone(match,result.stdout)
                self.assertTrue(all(math.isfinite(float(x)) for x in match.groups()))
                self.assertEqual(validate_capture(capture,kind),report['captures'][kind])
                print(result.stdout,end='')
        for path,sha in pins.items(): self.assertEqual(digest(Path(path)),sha)

    def test_real_operator_graph(self):
        self.check_graph('/usr/bin/gcc','/usr/bin/g++',[])

    def test_sanitized_operator_graph(self):
        self.check_graph('/usr/bin/clang','/usr/bin/clang++',
            ['-fsanitize=address,undefined','-fno-omit-frame-pointer'])


if __name__=='__main__': unittest.main()
