#!/usr/bin/env python3
"""Successor probe with matrix types/shapes; does not alter the running probe."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from compile_context_attribution import DATABASE, ROOT, SOURCE, instrument

DETAIL = r'''
            if (examined != nullptr && examined->op == GGML_OP_MUL_MAT &&
                examined->src[0] != nullptr && examined->src[1] != nullptr) {
                const ggml_tensor * w = examined->src[0];
                const ggml_tensor * a = examined->src[1];
                std::fprintf(stderr,
                    "GGML_RISCV_QBS_CONTEXT_MATRIX graph_epoch=%llu current=%p examined=%p "
                    "weight_type=%d activation_type=%d w0=%lld w1=%lld w2=%lld w3=%lld "
                    "a0=%lld a1=%lld a2=%lld a3=%lld weight=%p activation=%p\n",
                    static_cast<unsigned long long>(current.graph_epoch),
                    static_cast<const void *>(origin), static_cast<const void *>(examined),
                    static_cast<int>(w->type), static_cast<int>(a->type),
                    static_cast<long long>(w->ne[0]), static_cast<long long>(w->ne[1]),
                    static_cast<long long>(w->ne[2]), static_cast<long long>(w->ne[3]),
                    static_cast<long long>(a->ne[0]), static_cast<long long>(a->ne[1]),
                    static_cast<long long>(a->ne[2]), static_cast<long long>(a->ne[3]),
                    static_cast<const void *>(w), static_cast<const void *>(a));
            }
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out'):
        parser.error('Use independent verification/out')
    original = SOURCE.read_text()
    candidate = instrument(original)
    marker = 'examined != nullptr ? ggml_op_name(examined->op) : "NONE", reason, decision);'
    if candidate.count(marker) != 1:
        raise ValueError('Observer structure drift')
    candidate = candidate.replace(marker, marker + DETAIL, 1)
    out.mkdir(parents=True, exist_ok=False)
    generated = out / 'qbs_context_attribution.cpp'
    generated.write_text(candidate)
    records = [r for r in json.loads(DATABASE.read_text()) if Path(r['file']).resolve() == SOURCE]
    if len(records) != 1:
        raise ValueError('Expected one production compile record')
    argv = shlex.split(records[0]['command'])
    argv[argv.index('-c')+1] = str(generated)
    argv[argv.index('-o')+1] = str(out / 'probe.o')
    argv += ['-iquote', str(SOURCE.parent)]
    (out / 'command.json').write_text(json.dumps(argv, indent=2) + '\n')
    with (out / 'compile.log').open('x') as log:
        run = subprocess.run(argv, cwd=records[0]['directory'], stdout=log,
                             stderr=subprocess.STDOUT, timeout=180)
    if SOURCE.read_text() != original:
        raise ValueError('Runtime source changed during compile')
    result = dict(state='COMPILE_ONLY_PASS' if run.returncode == 0 else 'FAIL',
                  runtime_modified=False, performance_measured=False,
                  source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                  generated_sha256=hashlib.sha256(generated.read_bytes()).hexdigest())
    if run.returncode == 0:
        result['object_sha256'] = hashlib.sha256((out / 'probe.o').read_bytes()).hexdigest()
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
