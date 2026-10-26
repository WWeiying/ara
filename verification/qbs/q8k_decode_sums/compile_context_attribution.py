#!/usr/bin/env python3
"""Compile a private context-lookahead probe without changing runtime decisions."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/qbs.cpp')
DATABASE = ROOT / 'verification/out/q8k-model-off-on-20261026-01/libraries/compile_commands.json'

OBSERVER = r'''
    // Diagnostic-only: log the original decision, then return it unchanged.
    const auto observe = [&](const ggml_tensor * examined, int index,
                             const char * reason, bool decision) {
        if (ggml_riscv_qbs_trace_activation_lifetime_enabled()) {
            const ggml_tensor * origin = params->cgraph != nullptr && params->node_index >= 0 &&
                params->node_index < ggml_graph_n_nodes(params->cgraph)
                ? ggml_graph_node(params->cgraph, params->node_index) : nullptr;
            std::fprintf(stderr,
                "GGML_RISCV_QBS_CONTEXT_LOOKAHEAD graph_epoch=%llu current_index=%d "
                "examined_index=%d current=%p examined=%p source=%p source_data=%p "
                "source_bytes=%zu write_data=%p write_bytes=%zu op=%s reason=%s decision=%d\n",
                static_cast<unsigned long long>(current.graph_epoch), params->node_index,
                index, static_cast<const void *>(origin), static_cast<const void *>(examined),
                static_cast<const void *>(current.source_tensor), current.source_data,
                current.source_tensor != nullptr ? ggml_nbytes(current.source_tensor) : 0,
                examined != nullptr ? examined->data : nullptr,
                examined != nullptr ? ggml_nbytes(examined) : 0,
                examined != nullptr ? ggml_op_name(examined->op) : "NONE", reason, decision);
        }
        return decision;
    };
'''


def instrument(text):
    start = text.index('static bool next_context_consumer_matches(')
    end = text.index('\nstatic qbs_activation_trace_link linked_activation', start)
    body = text[start:end]
    replacements = [
        ('return false;', 'return observe(nullptr, -1, "missing_graph", false);'),
        ('return false;', 'return observe(next_node, node_index, "may_modify_activation", false);'),
        ('return false;', 'return observe(next_node, node_index, "expert_context_consumer", false);'),
        ('return false;', 'return observe(next_node, node_index, "ineligible_matrix", false);'),
        ('return same_cross_op_identity(current, next);',
         'return observe(next_node, node_index, "identity_match", same_cross_op_identity(current, next));'),
        ('return false;', 'return observe(nullptr, node_count, "end_of_graph", false);'),
    ]
    if body.count('return false;') != 5 or body.count('return same_cross_op_identity(current, next);') != 1:
        raise ValueError('Lookahead control structure changed; review before instrumentation')
    # Ordered substitutions retain every original branch and its decision.
    for old, new in replacements:
        body = body.replace(old, new, 1)
    position = body.index('{') + 1
    body = body[:position] + OBSERVER + body[position:]
    return text[:start] + body + text[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out'):
        parser.error('Use an independent verification/out directory')
    out.mkdir(parents=True, exist_ok=False)
    raw = SOURCE.read_bytes()
    generated = out / 'qbs_context_attribution.cpp'
    generated.write_text(instrument(raw.decode()))
    records = [r for r in json.loads(DATABASE.read_text()) if Path(r['file']).resolve() == SOURCE]
    if len(records) != 1:
        raise ValueError('Expected one production QBS compile record')
    record = records[0]
    argv = shlex.split(record['command'])
    argv[argv.index('-c') + 1] = str(generated)
    argv[argv.index('-o') + 1] = str(out / 'probe.o')
    argv += ['-iquote', str(SOURCE.parent)]
    (out / 'command.json').write_text(json.dumps(argv, indent=2) + '\n')
    with (out / 'compile.log').open('x') as log:
        run = subprocess.run(argv, cwd=record['directory'], stdout=log,
                             stderr=subprocess.STDOUT, timeout=180)
    if SOURCE.read_bytes() != raw:
        raise ValueError('Runtime source changed during probe build')
    result = dict(state='COMPILE_ONLY_PASS' if run.returncode == 0 else 'FAIL',
                  returncode=run.returncode, runtime_modified=False, performance_measured=False,
                  source_sha256=hashlib.sha256(raw).hexdigest(),
                  generated_sha256=hashlib.sha256(generated.read_bytes()).hexdigest())
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
