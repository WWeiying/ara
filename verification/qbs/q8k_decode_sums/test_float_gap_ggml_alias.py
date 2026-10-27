"""Actual GGML tensor/span checks for the extracted production write guard.

No fake ggml_nbytes or tensor definition is used. This tests alias admission,
not graph execution, QBS arithmetic, or native context ownership.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from compile_float_gap_candidate import SOURCE, candidate

LLAMA = SOURCE.parents[4]

PREFIX = r'''
#include "ggml.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
struct qbs_cross_op_identity {
    const ggml_tensor *source_tensor;
    const void *source_data;
};
'''

SUFFIX = r'''
int main() {
    ggml_init_params p{1024*1024, nullptr, false};
    auto *ctx = ggml_init(p); assert(ctx);
    auto *storage = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, 4096);
    auto *input = ggml_view_1d(ctx, storage, 16, 256);
    qbs_cross_op_identity id{input, input->data};
    unsigned checks=0;
    auto expect = [&](ggml_tensor *t, bool want) {
        assert(node_may_modify_activation(t,id)==want); ++checks;
    };
    auto *output = ggml_view_1d(ctx,storage,16,256);
    output->op=GGML_OP_MUL_MAT;
    expect(output,true);  // exact overlap
    output->data=static_cast<char *>(storage->data)+252;
    expect(output,true);  // overlaps from below
    output->data=static_cast<char *>(storage->data)+316;
    expect(output,true);  // last source element
    output->data=static_cast<char *>(storage->data)+320;
    expect(output,false); // immediately after
    output->data=static_cast<char *>(storage->data)+192;
    expect(output,false); // immediately before
    auto *strided = ggml_view_2d(ctx,storage,4,2,256,0);
    strided->op=GGML_OP_MUL_MAT;
    assert(ggml_nbytes(strided)==272);
    expect(strided,true); // second row overlaps despite small element count
    auto *source_view = ggml_view_2d(ctx,storage,4,2,256,256);
    id={source_view,source_view->data};
    output->data=static_cast<char *>(storage->data)+512;
    expect(output,true); // second source row
    output->data=static_cast<char *>(storage->data)+528;
    expect(output,false);
    output->data=nullptr; expect(output,true);
    output->data=storage->data;
    id.source_data=nullptr; expect(output,true);
    id={input,input->data};
    output->op=GGML_OP_CUSTOM; expect(output,true);
    output->op=GGML_OP_OPT_STEP_ADAMW; expect(output,true);
    // Metadata-only views do not write, including aliases of the input.
    output->data=input->data;
    for (auto op : {GGML_OP_VIEW,GGML_OP_RESHAPE,GGML_OP_TRANSPOSE,GGML_OP_PERMUTE}) {
        output->op=op; expect(output,false);
    }
    ggml_free(ctx);
    std::printf("FLOAT_GAP_GGML_ALIAS_PASS checks=%u\n",checks);
}
'''


class GGMLAliasTest(unittest.TestCase):
    def test_actual_tensor_spans(self):
        text = candidate(SOURCE.read_text())
        first = text.index('static bool node_may_modify_activation(')
        end = text.index('\nstatic bool next_context_consumer_matches(', first)
        # Compile the current GGML implementation itself, avoiding a possibly
        # stale host shared library with a different tensor layout.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'alias.cpp'
            source.write_text(PREFIX + '\n#include <initializer_list>\n' + text[first:end] + SUFFIX)
            common = ['-I', str(LLAMA/'include'), '-I', str(LLAMA/'src')]
            objects = []
            for filename in ('ggml.c', 'ggml-alloc.c', 'ggml-quants.c'):
                obj = root / (filename+'.o')
                result = subprocess.run(['clang','-O1','-D_GNU_SOURCE','-std=c11',
                                '-DGGML_VERSION="alias-test"','-DGGML_COMMIT="source-test"',
                                '-ffunction-sections','-fdata-sections', *common,
                                '-c',str(LLAMA/'src'/filename),'-o',str(obj)],
                               capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                objects.append(str(obj))
            result = subprocess.run(['clang++','-std=c++17','-O1','-fsanitize=undefined',
                            *common,str(source),str(LLAMA/'src/ggml-threading.cpp'),
                            *objects,'-Wl,--gc-sections',
                            '-lm','-pthread','-o',str(root/'test')],
                           capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(root/'test')],check=True,
                                    capture_output=True,text=True,timeout=10)
            self.assertEqual(result.stdout.strip(),'FLOAT_GAP_GGML_ALIAS_PASS checks=16')


if __name__ == '__main__':
    unittest.main()
