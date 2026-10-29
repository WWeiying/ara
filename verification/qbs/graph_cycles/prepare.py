#!/usr/bin/env python3
"""Create an isolated CPU-loop probe; never edit the llama.cpp source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def instrument(text, source):
    additions = []
    def insert(anchor, body):
        if text.count(anchor) != 1:
            raise ValueError('Ambiguous integration anchor: ' + anchor)
        offset = text.index(anchor)
        if offset and text[offset-1] != '\n':
            raise ValueError('Anchor is not a complete line')
        line = text[:offset].count('\n') + 1
        additions.append((offset, '#ifdef GGML_RISCV_NODE_CYCLES\n' + body +
                          '\n#endif\n#line %d %s\n' % (line, json.dumps(str(source)))))
    insert('static thread_ret_t ggml_graph_compute_thread(void * data) {', '''#include "records.h"
#if !defined(__riscv) || __riscv_xlen != 64
#error "Node cycle probe requires RV64; host clocks are not RTL cycles"
#endif
static inline uint64_t qbs_node_clock(void) {
    uint64_t value;
    __asm__ volatile("rdcycle %0" : "=r"(value) : : "memory");
    return value;
}
static bool qbs_node_probe_quiet(void) {
    const char *names[] = {"GGML_RISCV_QBS_TRACE", "GGML_RISCV_QBS_TRACE_CALLS",
        "GGML_RISCV_QBS_TRACE_LIFETIME", "GGML_RISCV_QBS_TRACE_M4_PREPARE",
        "GGML_RISCV_AKV_TRACE"};
    for (size_t i=0; i<sizeof(names)/sizeof(names[0]); ++i) {
        const char *value=getenv(names[i]);
        if (value && value[0] && strcmp(value,"0")!=0) return false;
    }
    return true;
}
''')
    insert('    for (int node_n = 0; node_n < cgraph->n_nodes && atomic_load_explicit(&tp->abort, memory_order_relaxed) != node_n; node_n++) {', '''    struct qbs_graph_cycles qbs_cycles = {0};
    struct qbs_graph_cycle_record *qbs_records = NULL;
    const char *qbs_requested = getenv("GGML_RISCV_NODE_CYCLES");
    if (qbs_requested && strcmp(qbs_requested,"1")==0 && params.ith==0 &&
        params.nth==1 && !riscv_model_observe && qbs_node_probe_quiet() &&
        cgraph->n_nodes>0 && (size_t)cgraph->n_nodes<=SIZE_MAX/sizeof(*qbs_records)) {
        qbs_records = malloc((size_t)cgraph->n_nodes*sizeof(*qbs_records));
        qbs_graph_cycles_begin(&qbs_cycles,qbs_records,(size_t)cgraph->n_nodes,
            cgraph->n_nodes,params.ith,params.nth,params.graph_epoch,qbs_node_clock());
    }
''')
    insert('        const int n_fused = ggml_cpu_try_fuse_ops(cgraph, node_n, &params, cplan);', '''        const int qbs_first_node = node_n;
        const uint64_t qbs_node_begin = qbs_cycles.active ? qbs_node_clock() : 0;
''')
    insert('        struct ggml_tensor * result_node = cgraph->nodes[node_n];', '''        if (qbs_cycles.active) {
            const uint64_t qbs_node_end = qbs_node_clock();
            qbs_graph_cycles_append(&qbs_cycles,qbs_first_node,node_n,node->op,
                                    qbs_node_begin,qbs_node_end);
        }
''')
    insert('    if (state->ith == 0 && riscv_model_observe) {\n        fprintf(stderr, "GGML_RISCV_MODEL_GRAPH_END', '''    if (qbs_records) {
        const uint64_t qbs_graph_end = qbs_node_clock();
        const int qbs_ok = qbs_graph_cycles_finish(&qbs_cycles,qbs_graph_end,
                                                 tp->ec==GGML_STATUS_SUCCESS);
        fprintf(stderr,"GGML_NODE_CYCLES graph=%" PRIu64 " valid=%d records=%zu elapsed=%" PRIu64
                " node_sum=%" PRIu64 " clock=rdcycle threads=1\\n",qbs_cycles.epoch,qbs_ok,
                qbs_cycles.count,qbs_cycles.end-qbs_cycles.begin,qbs_cycles.node_sum);
        if (qbs_ok) for (size_t i=0; i<qbs_cycles.count; ++i) {
            const struct qbs_graph_cycle_record *r=&qbs_records[i];
            const struct ggml_tensor *t=cgraph->nodes[r->first];
            fprintf(stderr,"GGML_NODE_CYCLE graph=%" PRIu64 " first=%d last=%d op=%d cycles=%" PRIu64
                    " ne=%" PRId64 ",%" PRId64 ",%" PRId64 ",%" PRId64 "\\n",
                    qbs_cycles.epoch,r->first,r->last,r->op,r->end-r->begin,
                    t->ne[0],t->ne[1],t->ne[2],t->ne[3]);
        }
        free(qbs_records);
    }
''')
    for offset, body in sorted(additions, reverse=True):
        text = text[:offset] + body + text[offset:]
    return '#line 1 %s\n' % json.dumps(str(source)) + text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    source = args.source.resolve(strict=True)
    raw = source.read_bytes()
    transformed = instrument(raw.decode(), source)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'ggml-cpu.c').write_text(transformed)
    shutil.copyfile(HERE/'records.h', args.output/'records.h')
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    report = dict(state='PREPARED_NOT_VALIDATED', source=str(source),
                  source_sha256=hashlib.sha256(raw).hexdigest(),
                  artifacts={str(x.resolve()):digest(x) for x in
                             (args.output/'ggml-cpu.c',args.output/'records.h',Path(__file__))})
    (args.output/'preparation.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
