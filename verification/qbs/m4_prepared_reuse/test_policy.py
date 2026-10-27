"""Exercise policy against actual GGML graph/tensor APIs with UBSan."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GGML=Path('/home/wangwy/llama/llama.cpp/ggml')


class PolicyTest(unittest.TestCase):
    def test_actual_ggml_graph(self):
        with tempfile.TemporaryDirectory(prefix='m4-policy-') as d:
            out=Path(d);objects=[]
            common=['-I'+str(GGML/'include'),'-I'+str(GGML/'src')]
            for name in ('ggml.c','ggml-alloc.c','ggml-quants.c'):
                obj=out/(name+'.o')
                subprocess.run(['clang','-O1','-D_GNU_SOURCE','-std=c11',
                    '-DGGML_VERSION="m4-policy"','-DGGML_COMMIT="source-test"',
                    '-ffunction-sections','-fdata-sections',*common,'-c',str(GGML/'src'/name),'-o',str(obj)],
                    check=True,capture_output=True,text=True,timeout=60)
                objects.append(str(obj))
            compiled=subprocess.run(['clang++','-O1','-std=c++17','-fsanitize=undefined','-fno-sanitize-recover=all',
                *common,'-I'+str(ROOT/'software/qbs/ggml'),str(HERE/'policy_test.cpp'),
                str(GGML/'src/ggml-threading.cpp'),*objects,'-Wl,--gc-sections','-lm','-pthread','-o',str(out/'test')],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            run=subprocess.run([str(out/'test')],check=True,capture_output=True,text=True,timeout=10)
            self.assertEqual(run.stdout.strip(),'M4_POLICY_PASS checks=35')


if __name__=='__main__':unittest.main()
