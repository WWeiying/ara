#!/usr/bin/env python3
"""Bounded strided-K panel tests; not performance or hardware evidence."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


class PanelTest(unittest.TestCase):
    def run_compiler(self,compiler,flags):
        with tempfile.TemporaryDirectory(prefix='prefix-panel-') as directory:
            binary=Path(directory)/'test'
            subprocess.run([compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                '-fno-fast-math','-ffp-contract=off',*flags,'-I'+str(ROOT),
                '-I'+str(ROOT/'software/qbs/include'),HERE/'test_prefix_panel.c',
                ROOT/'software/akv/experimental/quantized_kv/runtime.c',
                ROOT/'software/qbs/src/qbs_runtime.c',ROOT/'verification/qbs/qbs_ref.c',
                '-lm','-o',binary],check=True,timeout=120)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout,'PREFIX_PANEL_PASS cases=24 contiguous_no_copy=1 '
                'visible_union_once=1 failure_restores_context=1\n')

    def test_gcc(self): self.run_compiler(shutil.which('gcc'),[])
    def test_ubsan(self):
        self.run_compiler('/usr/bin/clang',['-fsanitize=undefined','-fno-sanitize-recover=undefined'])


if __name__=='__main__': unittest.main()
