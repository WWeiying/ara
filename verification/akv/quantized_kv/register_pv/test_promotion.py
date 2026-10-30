"""Promotion starts with the measured implementation, not an untested rewrite."""
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[3] / 'software/akv/experimental/quantized_kv/register_pv'


class PromotionTest(unittest.TestCase):
    def test_guarded_entry_identity(self):
        text=(HERE/'runtime_entry_guard_candidate.c').read_text()
        text=text.replace('/* Successor experiment while the promoted runtime is sealed by model tests. */',
                          '/* Public entry: sample CSRs before any potentially vectorized library call. */')
        text=text.replace('"software/akv/experimental/quantized_kv/register_pv/runtime.h"','"runtime.h"')
        text=text.replace('"software/akv/experimental/quantized_kv/register_pv/runtime.c"','"runtime.c"')
        self.assertEqual((SHARED/'entry.c').read_text(),text)

    def test_cpp_c_linkage(self):
        root=HERE.parents[3]
        source='''#include "software/akv/experimental/quantized_kv/register_pv/runtime.h"
extern "C" size_t quant_register_workspace_bytes(void);
extern "C" int quant_register_execute(const akv_quant_selection_input_t *,
    const akv_quant_native_bindings_t *, void *, size_t, akv_quant_strided_report_t *);
'''
        subprocess.run(['g++','-x','c++','-fsyntax-only','-Werror',
                        '-I'+str(root),'-I'+str(root/'software/qbs/include'),'-'],
                       input=source,text=True,check=True,capture_output=True,timeout=30)

    def test_measured_source_identity(self):
        for old, new in (('candidate.h', 'kernel.h'),
                         ('online_candidate.h', 'online.h'),
                         ('runtime_candidate.h', 'runtime.h'),
                         ('runtime_candidate.c', 'runtime.c')):
            text = (HERE / old).read_text()
            text = text.replace('"candidate.h"', '"kernel.h"')
            text = text.replace('"online_candidate.h"', '"online.h"')
            text = text.replace('"runtime_candidate.h"', '"runtime.h"')
            text = text.replace('/* Experiment only: production scale/fused-MAD arithmetic and immutable buffers.',
                                '/* Opt-in RVV path: production scale/fused-MAD arithmetic and immutable buffers.')
            if new == 'runtime.h':
                text = text.replace('#include "software/akv/experimental/quantized_kv/runtime_strided.h"\n',
                    '#include "software/akv/experimental/quantized_kv/runtime_strided.h"\n\n#ifdef __cplusplus\nextern "C" {\n#endif\n')
                position = text.rfind('\n#endif\n')
                text = text[:position] + '\n#ifdef __cplusplus\n}\n#endif\n' + text[position:]
            with self.subTest(source=old):
                self.assertEqual((SHARED / new).read_text(), text)


if __name__ == '__main__':
    unittest.main()
