"""Execute extracted production lookahead/write guards with explicit graph fixtures.

This is a control-policy test, not a replacement for a real GGML model gate.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from compile_float_gap_candidate import SOURCE, candidate

PREFIX = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
enum { GGML_OP_NONE, GGML_OP_RESHAPE, GGML_OP_VIEW, GGML_OP_PERMUTE,
 GGML_OP_TRANSPOSE, GGML_OP_MAP_CUSTOM1, GGML_OP_MAP_CUSTOM2, GGML_OP_MAP_CUSTOM3,
 GGML_OP_CUSTOM, GGML_OP_OPT_STEP_ADAMW, GGML_OP_OPT_STEP_SGD,
 GGML_OP_MUL_MAT, GGML_OP_MUL_MAT_ID, GGML_OP_ROPE };
enum { GGML_TYPE_F32, GGML_TYPE_F16, GGML_TYPE_Q4_K };
constexpr int QBS_WEIGHT_PROFILE_INVALID = -1;
struct ggml_tensor {
 int op=GGML_OP_NONE, type=GGML_TYPE_F32;
 ggml_tensor *src[2]={}; void *data=nullptr; size_t bytes=64;
 bool eligible=false;
};
struct qbs_cross_op_identity {
 uint64_t graph_epoch=1; const ggml_tensor *source_tensor=nullptr;
 const void *source_data=nullptr;
};
struct graph { std::vector<ggml_tensor *> nodes; };
struct ggml_compute_params { graph *cgraph; int node_index; uint64_t graph_epoch=1; };
size_t ggml_nbytes(const ggml_tensor *n) { return n->bytes; }
int ggml_graph_n_nodes(graph *g) { return g->nodes.size(); }
ggml_tensor *ggml_graph_node(graph *g,int i) { return g->nodes.at(i); }
bool ggml_riscv_qbs_trace_activation_lifetime_enabled() { return false; }
const char *ggml_op_name(int) { return "test"; }
bool same_cross_op_identity(const qbs_cross_op_identity &a,const qbs_cross_op_identity &b) {
 return a.graph_epoch==b.graph_epoch && a.source_tensor==b.source_tensor && a.source_data==b.source_data;
}
bool context_identity_for_node(const ggml_tensor *n,uint64_t epoch,qbs_cross_op_identity *id) {
 if (!n->eligible) return false;
 *id={epoch,n->src[1],n->src[1]->data}; return true;
}
bool future_float_profile=false;
struct profile { int weight; };
profile profile_for_type(int type) {
 return {type==GGML_TYPE_Q4_K || future_float_profile ? 1 : QBS_WEIGHT_PROFILE_INVALID};
}
'''
SUFFIX = r'''
int main() {
 ggml_tensor input, weight, a, origin, gap, next, other;
 input.data=reinterpret_cast<void *>(0x1000);
 a.data=reinterpret_cast<void *>(0x3000);
 gap.op=GGML_OP_MUL_MAT; gap.data=reinterpret_cast<void *>(0x2000);
 gap.src[0]=&weight; gap.src[1]=&a;
 next.op=GGML_OP_MUL_MAT; next.data=reinterpret_cast<void *>(0x4000);
 next.eligible=true; next.src[1]=&input;
 graph g{{&origin,&gap,&next}};
 ggml_compute_params p{&g,0};
 qbs_cross_op_identity current{1,&input,input.data};
 unsigned checks=0;
 auto expect=[&](bool want) { assert(next_context_consumer_matches(&p,current)==want); ++checks; };
 expect(true);
 weight.type=GGML_TYPE_F16; expect(true);
 gap.data=input.data; expect(false);
 gap.data=reinterpret_cast<void *>(0x0ff0); expect(false);
 gap.data=reinterpret_cast<void *>(0x1040); expect(true);
 gap.data=reinterpret_cast<void *>(0x2000);
 weight.type=GGML_TYPE_Q4_K; expect(false);
 weight.type=GGML_TYPE_F32; a.type=GGML_TYPE_F16; expect(false);
 a.type=GGML_TYPE_F32; future_float_profile=true; expect(false);
 future_float_profile=false; gap.op=GGML_OP_MUL_MAT_ID; expect(false);
 gap.op=GGML_OP_CUSTOM; expect(false);
 gap.op=GGML_OP_MUL_MAT; gap.src[0]=nullptr; expect(false);
 gap.src[0]=&weight; gap.src[1]=nullptr; expect(false);
 gap.src[1]=&a; other.data=input.data; next.src[1]=&other; expect(false);
 next.src[1]=&input; next.data=input.data; expect(false);
 next.data=reinterpret_cast<void *>(0x4000); expect(true);
 p.cgraph=nullptr; expect(false);
 p.cgraph=&g; p.node_index=2; expect(false);
 printf("FLOAT_GAP_POLICY_PASS checks=%u\n",checks);
}
'''


class FloatGapTest(unittest.TestCase):
    def test_actual_control_paths(self):
        text = candidate(SOURCE.read_text())
        first = text.index('static bool node_may_modify_activation(')
        last = text.index('\nstatic qbs_activation_trace_link linked_activation', first)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'policy.cpp'
            source.write_text(PREFIX + text[first:last] + SUFFIX)
            build = subprocess.run(['clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=undefined', str(source), '-o', str(root / 'test')],
                           capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(root / 'test')], check=True, capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.stdout.strip(), 'FLOAT_GAP_POLICY_PASS checks=17')


if __name__ == '__main__':
    unittest.main()
