"""The runtime kernel lives in software; verification keeps compatibility includes."""
from pathlib import Path
import re
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PRODUCTION=ROOT/'software/akv/experimental/quantized_kv/prefill'
FILES=('prefix_schedule.h','native_prefix.h','prefix_panel.h','admission.h',
       'execute.h','ggml_map.h','ggml_entry.h','ggml_entry.c')


class SoftwareLayoutTest(unittest.TestCase):
    def test_compatibility_only(self):
        for name in FILES:
            with self.subTest(name=name):
                expected='/* Compatibility entry: the canonical implementation lives in software/. */\n'+\
                         f'#include "software/akv/experimental/quantized_kv/prefill/{name}"\n'
                self.assertEqual((HERE/name).read_text(),expected)
                source=(PRODUCTION/name).read_text()
                self.assertNotIn('verification/',source)
                for include in re.findall(r'^#include "([^"]+)"',source,re.M):
                    target=ROOT/include if include.startswith('software/') else PRODUCTION/include
                    self.assertTrue(target.is_file(),str(target))

    def test_default_backend_directory(self):
        cmake=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/CMakeLists.txt').read_text()
        self.assertIn('set(GGML_RISCV_AKV_PREFILL_DIR "${GGML_QUANT_KV_DIR}/prefill" CACHE PATH',cmake)
        self.assertIn('get_filename_component(GGML_PREFILL_ROOT "${GGML_QUANT_KV_DIR}/../../../.." ABSOLUTE)',cmake)


if __name__=='__main__':unittest.main()
