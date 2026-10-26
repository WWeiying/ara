import pathlib
import re
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
RISCV_CC = '/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc'


class StrideCheck(unittest.TestCase):
    def test_boundary_and_random_equivalence(self):
        with tempfile.TemporaryDirectory() as tmp:
            for cc in ('/usr/bin/gcc', '/usr/bin/clang'):
                binary = pathlib.Path(tmp) / pathlib.Path(cc).name
                subprocess.run([cc, '-std=c11', '-O3', '-Wall', '-Wextra', '-Werror',
                                '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error',
                                str(HERE/'check.c'), '-o', str(binary)],
                               check=True, timeout=30)
                result = subprocess.run([str(binary)], check=True, timeout=30,
                                        capture_output=True, text=True)
                self.assertIn('STRIDE_EQUIVALENCE_PASS checks=1010575 size_bits=64', result.stdout)

    def test_riscv_no_divide(self):
        with tempfile.TemporaryDirectory() as tmp:
            assembly = pathlib.Path(tmp) / 'candidate.s'
            subprocess.run([RISCV_CC, '-march=rv64gc', '-mabi=lp64d', '-O3',
                            '-DASSEMBLY_ONLY', '-S', str(HERE/'check.c'), '-o', str(assembly)],
                           check=True, timeout=30)
            text = assembly.read_text()
            self.assertIsNone(re.search(r'\b(?:divu?w?|remu?w?)\b', text))
            self.assertRegex(text, r'\bmulhu\b')


if __name__ == '__main__':
    unittest.main()
