#!/usr/bin/env python3
"""Private candidate: retain activation context across non-QBS float matmul."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from compile_context_attribution import DATABASE, ROOT, SOURCE, instrument

OLD = '''            // A different matrix shape may still acquire a context for a tail.
            if (next_node->op == GGML_OP_MUL_MAT) {
                return false;
            }'''
NEW = '''            // Quantized matrices may acquire a context even for a tail.
            // Ordinary float matrices do not enter the QBS block interface.
            // The input-write check above remains mandatory before this skip.
            if (next_node->op == GGML_OP_MUL_MAT) {
                const ggml_tensor * weights = next_node->src[0];
                const ggml_tensor * activation = next_node->src[1];
                if (weights != nullptr && activation != nullptr &&
                    (weights->type == GGML_TYPE_F32 || weights->type == GGML_TYPE_F16) &&
                    activation->type == GGML_TYPE_F32 &&
                    profile_for_type(weights->type).weight == QBS_WEIGHT_PROFILE_INVALID) {
                    continue;
                }
                return false;
            }'''


def candidate(text):
    if text.count(OLD) != 1:
        raise ValueError('Reviewed lookahead barrier changed')
    return text.replace(OLD, NEW, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out'):
        parser.error('Use independent verification/out')
    original = SOURCE.read_text()
    generated_text = instrument(candidate(original))
    out.mkdir(parents=True, exist_ok=False)
    generated = out / 'qbs_context_attribution.cpp'
    generated.write_text(generated_text)
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
        raise ValueError('Runtime source drift')
    result = dict(state='COMPILE_ONLY_PASS' if run.returncode == 0 else 'FAIL',
                  private_policy_candidate=True, runtime_modified=False, performance_measured=False,
                  source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                  generated_sha256=hashlib.sha256(generated.read_bytes()).hexdigest())
    if run.returncode == 0:
        result['object_sha256'] = hashlib.sha256((out / 'probe.o').read_bytes()).hexdigest()
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
