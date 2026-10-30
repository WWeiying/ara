#!/usr/bin/env python3
"""Compile an isolated full-TU candidate; never modify a live runtime build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

from test_candidate import HERE, LLAMA, RELATIVE, OLD, NEW, pinned_source


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compile-commands', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    database = args.compile_commands.resolve(strict=True)
    source = LLAMA / RELATIVE
    original = pinned_source(source.read_bytes())
    records = [r for r in json.loads(database.read_text()) if Path(r['file']).resolve() == source]
    if len(records) != 1:
        raise ValueError('Need exactly one actual repack compile command')
    record = records[0]
    command = shlex.split(record['command'])
    march = [x for x in command if x.startswith('-march=')]
    required = ('-O3', '-DGGML_USE_RISCV_QBS', '-DGGML_USE_RISCV_AKV', '-DGGML_USE_RISCV_QUANT_KV')
    if not all(x in command for x in required) or march[-1:] != ['-march=rv64gcv_zfh_zvfh']:
        raise ValueError('Not the current combined production compile configuration')
    if any(x.startswith(('-flto', '-ffast-math', '-ffinite-math-only', '-MF', '-MD', '-MMD')) for x in command):
        raise ValueError('Unsupported compile/dependency flags; review before use')
    if command[command.index('-c') + 1] != str(source):
        raise ValueError('Unexpected source operand')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    copied = out / RELATIVE
    copied.parent.mkdir(parents=True)
    shutil.copyfile(source, copied)
    patch = HERE / 'enable_q8k.patch'
    patch_env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(out.parent))
    subprocess.run(['git', 'apply', str(patch)], cwd=out, env=patch_env,
                   check=True, capture_output=True)
    if copied.read_text() != original.replace(OLD, NEW):
        raise ValueError('Candidate changed more than the two approved guards')
    command[command.index('-c') + 1] = str(copied)
    command[command.index('-o') + 1] = str(out / 'candidate.o')
    command += ['-iquote', str(source.parent)]
    # Full header inventory is pinned before compilation, not just after it.
    inputs = {source, copied, database, patch, Path(__file__).resolve(),
              HERE / 'test_candidate.py', Path(command[0]).resolve()}
    include_roots = [Path(x[2:]).resolve() for x in command if x.startswith('-I')]
    for root in set(include_roots):
        inputs.update(p for p in root.rglob('*') if p.is_file() and
                      p.suffix in {'.h', '.hpp', '.inl', '.inc'})
    pins = {str(p): digest(p) for p in sorted(inputs)}
    (out / 'inputs.json').write_text(json.dumps(pins, indent=2) + '\n')
    (out / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    start = time.monotonic()
    with (out / 'compile.log').open('x') as log:
        result = subprocess.run(command, cwd=record['directory'], stdout=log,
                                stderr=subprocess.STDOUT, timeout=600)
    if any(digest(Path(name)) != sha for name, sha in pins.items()):
        raise ValueError('Compile inputs changed')
    report = dict(state='COMPILE_ONLY_PASS' if result.returncode == 0 else 'COMPILE_FAIL',
                  exit_code=result.returncode, elapsed_seconds=time.monotonic() - start,
                  numerical_validation=False, performance_validation=False,
                  production_modified=False, effective_march=march[-1],
                  inputs_sha256=digest(out / 'inputs.json'),
                  command_sha256=digest(out / 'command.json'),
                  object_sha256=digest(out / 'candidate.o') if result.returncode == 0 else None)
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
