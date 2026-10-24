#!/usr/bin/env python3
"""Shared execution wiring with QBS reference; not production quantizer/native RTL proof."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class NativeContractTest(unittest.TestCase):
    def check_binary(self, compiler, sanitizer):
        with tempfile.TemporaryDirectory(prefix='quant-native-host-') as tmp:
            binary = Path(tmp)/'test'
            subprocess.run([compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                '-fno-fast-math','-ffp-contract=off',*sanitizer,'-I'+str(ROOT),
                '-I'+str(ROOT/'software/qbs/include'),HERE/'test_native.c',
                ROOT/'software/akv/experimental/quantized_kv/runtime.c',
                ROOT/'software/qbs/src/qbs_runtime.c',ROOT/'verification/qbs/qbs_ref.c',
                '-lm','-o',binary],check=True,timeout=120)
            result = subprocess.run([binary],capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout,'QUANT_NATIVE_HOST_PASS cases=96 reference=qbs_ref '
                'test_quantizer=integer_scale1 padding=1 fallback_before_callbacks=1 execution_failure_no_retry=1\n')
            print(result.stdout,end='')

    def test_common_execution(self):
        self.check_binary(shutil.which('gcc'),[])

    def test_sanitized_execution(self):
        self.check_binary('/usr/bin/clang',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])

    def test_cpp_backend_header(self):
        subprocess.run([shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),'-fsyntax-only','-x','c++','-'],
            input='#include "software/akv/experimental/quantized_kv/runtime.h"\nint main() { return 0; }\n',
            text=True,check=True,timeout=120)


if __name__ == '__main__':
    unittest.main()
