#!/usr/bin/env python3
"""Whole-operation Prefill admission, checked without issuing commands."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


class AdmissionTest(unittest.TestCase):
    def compile_and_run(self,compiler,flags):
        with tempfile.TemporaryDirectory(prefix='prefill-admission-') as directory:
            binary=Path(directory)/'test'
            subprocess.run([compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                '-fno-fast-math','-ffp-contract=off',*flags,'-I'+str(ROOT),
                '-I'+str(ROOT/'software/qbs/include'),HERE/'test_selector_aligned.c',
                ROOT/'software/akv/experimental/quantized_kv/runtime.c',
                ROOT/'software/qbs/src/qbs_runtime.c',ROOT/'verification/qbs/qbs_ref.c',
                '-lm','-o',binary],check=True,timeout=120)
            run=subprocess.run([binary],capture_output=True,text=True,timeout=60)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertEqual(run.stdout,'SELECTOR_ALIGNED_PASS cases=972 rejected=12 flags_equal=1 failed_plan_unchanged=1\n')

    def test_gcc(self): self.compile_and_run(shutil.which('gcc'),[])
    def test_ubsan(self):
        self.compile_and_run('/usr/bin/clang',['-fsanitize=undefined','-fno-sanitize-recover=undefined'])


if __name__=='__main__': unittest.main()
