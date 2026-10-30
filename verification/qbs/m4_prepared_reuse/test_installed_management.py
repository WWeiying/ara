"""Test promoted headers directly, independently of archived generated copies."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GGML=Path('/home/wangwy/llama/llama.cpp/ggml')
HEADERS=ROOT/'software/qbs/ggml'


def run(command,limit=60):
    result=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=limit)
    if result.returncode:
        raise AssertionError(f'Command failed: {command!r}\n{result.stdout}\n{result.stderr}')
    return result


class InstalledManagement(unittest.TestCase):
    def test_actual_installed_header_identity(self):
        for name in ('q8_K-prepared-cache.h','q8_K-prepared-reuse.h',
                     'm4-reuse-policy.h','rvv-byte-ops.h'):
            with self.subTest(header=name):
                self.assertEqual((HEADERS/name).read_bytes(),
                                 (GGML/'src/ggml-cpu/arch/riscv'/name).read_bytes())

    def test_canonical_cache_management(self):
        with tempfile.TemporaryDirectory(prefix='installed-m4-cache-') as d:
            out=Path(d)
            # Only the compatibility namespace differs from the archived suite.
            (out/'value_cache.hpp').write_text(
                '#include "q8_K-prepared-cache.h"\n'
                'namespace q8k_m4_experiment = ggml_riscv_q8_K_cache;\n')
            (out/'test.cpp').write_bytes((HERE/'cache_test.cpp').read_bytes())
            run(['clang++','-O1','-std=c++17','-Wall','-Wextra','-Werror',
                 '-fsanitize=undefined','-fno-sanitize-recover=all',
                 '-I'+str(ROOT/'software/qbs/include'),'-I'+str(HEADERS),
                 out/'test.cpp','-o',out/'test'])
            self.assertEqual(run([out/'test'],10).stdout.strip(),'PASS 8064 cache checks')

    def test_policy_shapes_formats_and_bounded_scan(self):
        with tempfile.TemporaryDirectory(prefix='installed-m4-policy-') as d:
            out=Path(d);objects=[]
            includes=['-I'+str(GGML/'include'),'-I'+str(GGML/'src')]
            for name in ('ggml.c','ggml-alloc.c','ggml-quants.c'):
                obj=out/(name+'.o')
                run(['clang','-O1','-D_GNU_SOURCE','-std=c11',
                     '-DGGML_VERSION="installed-policy-test"','-DGGML_COMMIT="source-test"',
                     '-ffunction-sections','-fdata-sections',*includes,
                     '-c',GGML/'src'/name,'-o',obj])
                objects.append(obj)
            run(['clang++','-O1','-std=c++17','-fsanitize=undefined',
                 '-fno-sanitize-recover=all',*includes,'-I'+str(HEADERS),
                 HERE/'policy_matrix_test.cpp',GGML/'src/ggml-threading.cpp',
                 *objects,'-Wl,--gc-sections','-lm','-pthread','-o',out/'test'])
            self.assertEqual(run([out/'test'],10).stdout.strip(),
                             'M4_POLICY_MATRIX_PASS checks=268')


if __name__=='__main__':unittest.main()
