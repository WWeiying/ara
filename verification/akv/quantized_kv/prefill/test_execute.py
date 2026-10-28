#!/usr/bin/env python3
"""Complete Prefill composition with a QBS reference executor, not RTL timing."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


class ExecuteTest(unittest.TestCase):
    def run_compiler(self,compiler,flags):
        with tempfile.TemporaryDirectory(prefix='prefill-execute-') as directory:
            binary=Path(directory)/'test'
            subprocess.run([compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                '-fno-fast-math','-ffp-contract=off',*flags,'-I'+str(ROOT),
                '-I'+str(ROOT/'software/qbs/include'),HERE/'test_execute.c',
                ROOT/'software/akv/experimental/quantized_kv/runtime.c',
                ROOT/'software/qbs/src/qbs_runtime.c',ROOT/'verification/qbs/qbs_ref.c',
                '-lm','-o',binary],check=True,timeout=120)
            run=subprocess.run([binary],capture_output=True,text=True,timeout=60)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertEqual(run.stdout,'PREFILL_EXECUTE_PASS kv_heads=2 queries=5 gqa=3 '
                'tail_rows=7 all_outputs=1 fallback_no_callbacks=1\n')

    def test_gcc(self):self.run_compiler(shutil.which('gcc'),[])
    def test_ubsan(self):
        self.run_compiler('/usr/bin/clang',['-fsanitize=undefined','-fno-sanitize-recover=undefined'])


if __name__=='__main__':unittest.main()
