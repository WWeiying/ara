#!/usr/bin/env python3
"""Insert a single-worker ns probe into an isolated, exactly pinned CPU source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = '2d9e4b8e4d38bb6cb64ca54abd4259f68c4aab7222fb2fb7391b973baf0958e3'
MACRO = 'GGML_STAGE1_NODE_NS'


def instrument(raw, source):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unsupported ggml-cpu.c SHA256; frozen input must not be edited')
    text = raw.decode('utf-8')
    additions = []

    def insert(anchor, body):
        if text.count(anchor) != 1:
            raise ValueError('Ambiguous integration anchor: ' + anchor)
        offset = text.index(anchor)
        if offset and text[offset - 1] != '\n':
            raise ValueError('Anchor is not a complete line')
        line = text[:offset].count('\n') + 1
        additions.append((offset, '#ifdef ' + MACRO + '\n' + body +
                          '\n#endif\n#line %d %s\n' % (line, json.dumps(str(source)))))

    insert('static thread_ret_t ggml_graph_compute_thread(void * data) {',
           '#include "node_probe.h"')
    insert('    for (int node_n = 0; node_n < cgraph->n_nodes && atomic_load_explicit(&tp->abort, memory_order_relaxed) != node_n; node_n++) {', '''    const int stage1_capture = params.ith == 0 &&
        stage1_node_probe_graph_begin(params.graph_epoch, cgraph->n_nodes,
                                     params.nth, riscv_model_observe);
''')
    insert('        const int n_fused = ggml_cpu_try_fuse_ops(cgraph, node_n, &params, cplan);', '''        const int stage1_first = node_n;
        if (stage1_capture) stage1_node_probe_unit_begin(stage1_first);
''')
    insert('        struct ggml_tensor * result_node = cgraph->nodes[node_n];', '''        if (stage1_capture) {
            stage1_node_probe_unit_end(node_n);
            for (int stage1_member = stage1_first; stage1_member <= node_n; ++stage1_member) {
                const struct ggml_tensor * stage1_node = cgraph->nodes[stage1_member];
                stage1_node_probe_member(stage1_member, stage1_node->op,
                    ggml_op_name(stage1_node->op), ggml_type_name(stage1_node->type),
                    stage1_node->name, stage1_node->ne);
            }
        }
''')
    insert('    if (state->ith == 0 && riscv_model_observe) {\n        fprintf(stderr, "GGML_RISCV_MODEL_GRAPH_END', '''    if (stage1_capture)
        stage1_node_probe_graph_end(tp->ec == GGML_STATUS_SUCCESS);
''')
    for offset, body in sorted(additions, reverse=True):
        text = text[:offset] + body + text[offset:]
    return '#line 1 %s\n' % json.dumps(str(source)) + text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Validate insertion without writing anything')
    mode.add_argument('--output', type=Path, help='New isolated output directory; never an existing tree')
    args = parser.parse_args(argv)
    source = args.source.resolve(strict=True)
    raw = source.read_bytes()
    transformed = instrument(raw, source)
    report = dict(state='HOST_PREPARED_NOT_BOARD_VALIDATED', source=str(source),
                  source_sha256=SOURCE_SHA256, macro=MACRO,
                  instrumented_sha256=hashlib.sha256(transformed.encode()).hexdigest(),
                  clock='CLOCK_MONOTONIC', units='software elapsed nanoseconds',
                  same_elf_runtime_switch='stage1_node_probe_phase_begin active=0/1')
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / 'ggml-cpu.c').write_text(transformed)
        for name in ('node_probe.h', 'node_probe.c'):
            shutil.copyfile(HERE / name, args.output / name)
        report['pins'] = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (args.output / 'ggml-cpu.c', args.output / 'node_probe.h',
                                       args.output / 'node_probe.c', Path(__file__))}
        (args.output / 'preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
