from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CC = '/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc'


class ProductionStride(unittest.TestCase):
    def test_actual_sdk_predicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            for cc in ('/usr/bin/gcc', '/usr/bin/clang'):
                output = Path(tmp)/Path(cc).name
                subprocess.run([cc, '-std=c11', '-O3', '-Wall', '-Wextra', '-Werror',
                                '-I'+str(ROOT), '-fsanitize=undefined',
                                '-fsanitize-undefined-trap-on-error',
                                str(HERE/'production_check.c'), '-o', str(output)],
                               check=True, capture_output=True, timeout=30)
                result = subprocess.run([str(output)], check=True, capture_output=True,
                                        text=True, timeout=30)
                self.assertIn('STRIDE_EQUIVALENCE_PASS checks=1010575 size_bits=64', result.stdout)

    def test_actual_sdk_riscv_predicate_has_no_division(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'probe.s'
            subprocess.run([CC, '-march=rv64gc', '-mabi=lp64d', '-O3', '-I'+str(ROOT),
                            '-DASSEMBLY_ONLY', '-S', str(HERE/'production_check.c'), '-o', str(output)],
                           check=True, capture_output=True, timeout=30)
            assembly = output.read_text()
            self.assertIsNone(re.search(r'\b(?:divu?w?|remu?w?)\b', assembly))
            self.assertRegex(assembly, r'\bmulhu\b')

    def test_complete_rvv_update_has_no_division(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'update.s'
            subprocess.run([CC, '-march=rv64gcv', '-mabi=lp64d', '-O3', '-I'+str(ROOT),
                            '-fno-fast-math', '-ffp-contract=off', '-DGROUPED_PV_COMPILE_ONLY',
                            '-S', str(HERE.parent/'test_kernel.c'), '-o', str(output)],
                           check=True, capture_output=True, timeout=30)
            assembly = output.read_text()
            self.assertIsNone(re.search(r'\b(?:divu?w?|remu?w?)\b', assembly))
            self.assertIn('vfmacc.vf', assembly)
            self.assertRegex(assembly, r'\bmulhu\b')


if __name__ == '__main__':
    unittest.main()
