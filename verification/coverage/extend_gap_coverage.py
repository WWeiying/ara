#!/usr/bin/env python3
"""Extend frozen VCS/DVE evidence with checked RVV and application tests.

Keep the previously hashed extension and scheduler unchanged. New RVV sources
can be selected without editing the frozen Makefrag/catalog. Verdicts, trace
audits and passed-only VDB admission remain those of the original scheduler.
"""
from pathlib import Path
import re

import extend_vcs_dve_batch as extension
from ara_verify.model import TestCase

batch = extension.batch
ROOT = batch.ROOT
SCRIPT = Path(__file__).resolve()


def select_tests(catalog, previous, names):
    old_names = {c.get('test') for c in previous['cases']}
    hashes = {c['elf_sha256'] for c in previous['cases']}
    selected, seen = [], set()
    for name in names:
        if name in old_names or name in seen:
            raise ValueError(f'duplicate or previously selected test: {name}')
        seen.add(name)
        if not re.fullmatch(r'(rvv|app):[A-Za-z0-9_]+', name):
            raise ValueError(f'unsupported test name: {name}')
        test = catalog.tests.get(name)
        kind, stem = name.split(':', 1)
        if test is None and kind == 'rvv':
            source = ROOT / 'apps/riscv-tests/isa/rv64uv' / (stem + '.c')
            if not source.is_file():
                raise ValueError(f'missing directed source: {source}')
            binary_name = 'rv64uv-ara-' + stem
            test = TestCase(name=name, kind='rvv', build_target='bin/' + binary_name,
                            binary=ROOT / 'apps/bin' / binary_name,
                            testcase=binary_name, timeout_s=300)
        if test is None or test.kind not in ('rvv', 'app') or not test.binary.is_file():
            raise ValueError(f'expected built self-checking test: {name}')
        digest = batch.sha256(test.binary)
        if digest in hashes:
            raise ValueError(f'duplicate ELF, not new stimulus: {name}')
        hashes.add(digest)
        selected.append((name, test, digest))
    if not selected:
        raise ValueError('empty extension')
    return selected


original_prepare = extension.prepare


def prepare(output, previous, selection):
    original_prepare(output, previous, selection)
    plan = batch.read(output / 'plan.json')
    for case in plan['cases']:
        if case['name'] in plan['reused']:
            continue
        if case['test'].startswith('app:'):
            app = ROOT / 'apps' / case['test'].split(':', 1)[1]
            sources = [p for p in app.rglob('*') if p.is_file() and
                       p.suffix in ('.c', '.h', '.cpp', '.S')]
            if not sources:
                raise ValueError(f'no application source: {app}')
            case['source_files'].update(batch.pins(sources))
    plan['files'].update(batch.pins([Path(extension.__file__)]))
    batch.save(output / 'plan.json', plan)
    batch.save(output / 'plan.sha256.json', batch.pins([output / 'plan.json']))
    batch.frozen(output, all_cases=True)


extension.SCRIPT = SCRIPT
batch.SCRIPT = SCRIPT
extension.select_tests = select_tests
extension.prepare = prepare

if __name__ == '__main__':
    raise SystemExit(extension.main())
