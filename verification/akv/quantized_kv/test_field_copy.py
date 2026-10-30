"""Small-copy semantics and actual GNU RISC-V code-generation checks, not timing."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GNU = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


class FieldCopyTest(unittest.TestCase):
    def test_host_bits_alignment_bounds_and_flags(self):
        for cc, extra in [('gcc', []), ('/usr/bin/clang',
                ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
            with self.subTest(cc=cc), tempfile.TemporaryDirectory() as tmp:
                binary = Path(tmp)/'test'
                subprocess.run([cc, '-O2', '-fno-builtin', '-fno-fast-math',
                    '-Wall', '-Wextra', '-Werror', *extra, '-I'+str(ROOT),
                    str(HERE/'test_field_copy.c'), '-lm', '-o', str(binary)],
                    check=True, timeout=120)
                result = subprocess.run([binary], capture_output=True, text=True,
                                        check=True, timeout=120)
                self.assertIn('FIELD_COPY_PASS', result.stdout)

    def test_actual_riscv_no_out_of_line_small_copies(self):
        self.assertTrue(GNU.is_file(), 'Required GNU toolchain missing')
        source = '''
#include "software/akv/experimental/quantized_kv/selection_strided.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"
int admit(const akv_quant_selection_input_t *p, akv_quant_selection_t *s) {
  return akv_quant_select_strided(p,s);
}
void decode(const void *p, float *out, size_t n) { akv_quant_q8_0_value(p,out,n); }
unsigned short read16(const void *p) {
  unsigned short x; AKV_QUANT_FIELD_COPY(&x,p,2); return x;
}
unsigned read32(const void *p) {
  unsigned x; AKV_QUANT_FIELD_COPY(&x,p,4); return x;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            obj = Path(tmp)/'probe.o'
            subprocess.run([str(GNU), '-O2', '-fno-builtin', '-fno-fast-math',
                '-march=rv64gcv_zvfh', '-mabi=lp64d', '-mstrict-align',
                '-I'+str(ROOT), '-I'+str(ROOT/'software/qbs/include'),
                '-x', 'c', '-', '-c', '-o', str(obj)], input=source, text=True,
                check=True, timeout=120)
            undefined = subprocess.check_output([str(GNU.with_name(
                'riscv64-unknown-elf-nm')), '-u', str(obj)], text=True)
            self.assertNotIn('memcpy', undefined)
            dis = subprocess.check_output([str(GNU.with_name(
                'riscv64-unknown-elf-objdump')), '-dr', str(obj)], text=True)
            for name in ('read16', 'read32'):
                body = dis.split('<'+name+'>:', 1)[1].split('\n\n', 1)[0]
                self.assertIn('lbu', body)  # Unknown alignment stays byte-safe.
            # A control with the old expression must retain a real call under
            # the same flags; absence above is not a toolchain-wide shortcut.
            subprocess.run([str(GNU), '-O2', '-fno-builtin', '-fno-fast-math',
                '-march=rv64gcv_zvfh', '-mabi=lp64d', '-mstrict-align',
                '-I'+str(ROOT), '-I'+str(ROOT/'software/qbs/include'),
                '-x', 'c', '-', '-c', '-o', str(obj)],
                input=source.replace('AKV_QUANT_FIELD_COPY(', 'memcpy('),
                text=True, check=True, timeout=120)
            old_undefined = subprocess.check_output([str(GNU.with_name(
                'riscv64-unknown-elf-nm')), '-u', str(obj)], text=True)
            self.assertIn('memcpy', old_undefined)


if __name__ == '__main__':
    unittest.main()
