import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('m4_vector_builder',HERE/'build_vector_cache_soc.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class GenerationTest(unittest.TestCase):
    def test_reviewed_delta_and_portable_management(self):
        text=(HERE/'value_cache.hpp').read_text();generated=builder.vector_header(text)
        self.assertNotIn('std::memcmp(',generated);self.assertNotIn('std::memcpy(',generated)
        self.assertEqual(generated.count('ggml_riscv_byte_ops::equal('),2)
        self.assertEqual(generated.count('ggml_riscv_byte_ops::copy('),3)
        with tempfile.TemporaryDirectory(prefix='m4-vector-cache-') as d:
            out=Path(d);(out/'value_cache.hpp').write_text(generated)
            (out/'test.cpp').write_bytes((HERE/'cache_test.cpp').read_bytes())
            subprocess.run(['clang++','-O1','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'software/qbs/include'),
                '-I'+str(ROOT/'software/qbs/ggml'),str(out/'test.cpp'),'-o',str(out/'test')],
                check=True,capture_output=True,text=True,timeout=60)
            run=subprocess.run([str(out/'test')],check=True,capture_output=True,text=True,timeout=10)
            self.assertEqual(run.stdout.strip(),'PASS 8064 cache checks')
    def test_refuse_unreviewed_source(self):
        with self.assertRaises(ValueError):builder.vector_header((HERE/'value_cache.hpp').read_text().replace('std::memcpy(','other_copy('))


if __name__=='__main__':unittest.main()
