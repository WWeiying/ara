"""Compile the production validator body on the host, without simulating RTL."""
import ctypes
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BenchmarkValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc')
        if not compiler:
            raise RuntimeError('host C compiler required')
        source = (ROOT / 'apps/llama_qwen25_real/common/qbs_benchmark_impl.h').read_text()
        bits = source[source.index('static uint32_t benchmark_float_bits('):
                      source.index('static inline qbs_descriptor_t benchmark_make_descriptor(')]
        validator = source[source.index('static __attribute__((noinline)) int benchmark_validate('):
                           source.index('\nint main(void) {')]
        cls.temp = tempfile.TemporaryDirectory()
        directory = Path(cls.temp.name)
        harness = '''
#include <stdint.h>
#include <string.h>
#define QBS_BENCH_OPERATIONS 2
#define BENCH_INPUTS 2
#define BENCH_ROWS 2
#define BENCH_ATOL 0.01f
#define BENCH_RTOL 0.001f
static float benchmark_golden_start[4];
static float outputs[8];
static float benchmark_actual(unsigned op, int input, int row) {
  return outputs[op * 4 + input * 2 + row];
}
''' + bits + validator + '''
int validate(const float *actual, const float *golden, float *abs, float *rel,
             uint64_t *checksum) {
  memcpy(outputs, actual, sizeof(outputs));
  memcpy(benchmark_golden_start, golden, sizeof(benchmark_golden_start));
  return benchmark_validate(abs, rel, checksum);
}
'''
        subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-shared', '-fPIC', '-x', 'c', '-', '-o', str(directory / 'test.so')],
                       input=harness, text=True, capture_output=True, check=True)
        cls.lib = ctypes.CDLL(str(directory / 'test.so'))
        cls.lib.validate.argtypes = [ctypes.POINTER(ctypes.c_float)] * 4 + [ctypes.POINTER(ctypes.c_uint64)]
        cls.lib.validate.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def validate(self, actual, golden):
        absolute, relative, checksum = ctypes.c_float(), ctypes.c_float(), ctypes.c_uint64()
        errors = self.lib.validate((ctypes.c_float * 8)(*actual),
            (ctypes.c_float * 4)(*golden), ctypes.byref(absolute),
            ctypes.byref(relative), ctypes.byref(checksum))
        return errors, absolute.value, relative.value, checksum.value

    def test_equal_finite(self):
        self.assertEqual(self.validate([0, -2, 3, 4] * 2, [0, -2, 3, 4])[:3], (0, 0, 0))

    def test_tolerance_and_failure(self):
        self.assertEqual(self.validate([1.005] * 8, [1] * 4)[0], 0)
        self.assertEqual(self.validate([1.1] * 8, [1] * 4)[0], 8)

    def test_nonfinite_actual(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(bad=bad):
                errors, absolute, relative, _ = self.validate([bad] + [1] * 7, [1] * 4)
                self.assertEqual(errors, 1)
                self.assertEqual((absolute, relative), (math.inf, math.inf))

    def test_nonfinite_reference(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(bad=bad):
                self.assertEqual(self.validate([1] * 8, [bad, 1, 1, 1])[0], 2)

    def test_equal_infinity_is_not_valid(self):
        self.assertEqual(self.validate([math.inf] * 8, [math.inf] * 4)[0], 8)

    def test_checksum_still_covers_invalid_outputs(self):
        valid = self.validate([1] * 8, [1] * 4)[3]
        invalid = self.validate([math.inf] + [1] * 7, [1] * 4)[3]
        self.assertNotEqual(valid, invalid)


if __name__ == '__main__':
    unittest.main()
