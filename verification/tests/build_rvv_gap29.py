#!/usr/bin/env python3
"""Isolated build/Spike precheck only. Does not invoke VCS."""
import build_rvv_memory_gaps as builder
import generate_rvv_gap29 as generator
import argparse
import hashlib
import json
from pathlib import Path
import sys

def pins(paths):
    return {str(p.absolute()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--prepared', type=Path, required=True)
    args, remaining = parser.parse_known_args()
    if args.prepared.exists() or '--spike' not in remaining or '--case' in remaining:
        parser.error('requires a fresh manifest and complete --spike precheck')
    root = generator.ROOT
    selection = Path(__file__).with_name('rvv_gap29_selection.json')
    tests = ['rvv:' + c[0] for c in generator.cases()]
    if json.loads(selection.read_text()) != {'tests': tests}:
        raise ValueError('selection mismatch')
    sources = [generator.DEST / (c[0] + '.c') for c in generator.cases()]
    for c, p in zip(generator.cases(), sources):
        if p.read_text() != generator.render(c):
            raise ValueError('source mismatch')
    sources += [selection, Path(__file__), Path(generator.__file__), Path(builder.__file__),
                Path(__file__).with_name('generate_rvv_memory_gaps.py'),
                Path(__file__).with_name('test_generate_rvv_gap29.py'),
                generator.DEST / 'vrvv_gap29_body.h']
    for directory in ('apps/common', 'apps/include', 'apps/riscv-tests/env',
                      'apps/riscv-tests/benchmarks/common', 'apps/riscv-tests/isa/macros'):
        sources += [p for p in (root / directory).rglob('*')
                    if p.is_file() and p.suffix in ('.c', '.h', '.S', '.ld')]
    sources += [root / 'install/riscv-llvm/bin/clang', root / 'install/riscv-llvm/bin/ld.lld',
                root / 'install/riscv-isa-sim/bin/spike']
    before = pins(sources)
    sys.argv = [sys.argv[0], *remaining]
    builder.cases = generator.cases
    builder.main()
    if before != pins(sources):
        raise ValueError('source/tool drift')
    out = Path(remaining[remaining.index('--output') + 1]).resolve()
    results_path = out / 'spike_results.json'
    results = json.loads(results_path.read_text())
    if [r['test'] for r in results] != tests or any(r['returncode'] for r in results):
        raise ValueError('incomplete precheck')
    artifacts = [results_path, out / 'build_commands.json']
    elf_hashes = set()
    for name, *_ in generator.cases():
        log = out / (name + '.spike.log')
        if b'PASSED:' not in log.read_bytes():
            raise ValueError('missing selfcheck PASS')
        elf = root / 'apps/bin' / ('rv64uv-ara-' + name)
        elf_hashes.update(pins([elf]).values())
        artifacts += [elf, out / (name + '.spike'), log]
    if len(elf_hashes) != len(tests):
        raise ValueError('duplicate ELF')
    record = dict(status='PREPARED', vcs_authorized=False, manual_launch_required=True,
                  append_after='original-image 521-case batch completion and user signal',
                  image_policy='original frozen image only; no repaired image',
                  coverage_benefit='unmeasured; reassess after 521 DVE', timeout_s=300,
                  tests=tests, selection=str(selection.resolve()), spike_passed=len(tests),
                  files=dict(before, **pins(artifacts)))
    with args.prepared.open('x') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print('PREPARED:', args.prepared)

if __name__ == "__main__":
    main()
