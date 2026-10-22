#!/usr/bin/env python3
"""Add distinct directed ELFs to a completed frozen VCS coverage campaign.

Reuse the existing scheduler, per-case oracle, VDB validation and DVE merger.
No RTL build, checker change or reinterpretation of prior failures is allowed.
"""
import argparse
from dataclasses import asdict
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import run_vcs_dve_batch as batch

ROOT, HERE = batch.ROOT, batch.HERE
SCRIPT = Path(__file__).resolve()
# Child invocations must return to this entry point, while retaining the
# original batch's validation and verdict rules unchanged.
batch.SCRIPT = SCRIPT


def select_tests(catalog, previous, names):
    old_names = {c.get('test') for c in previous['cases']}
    old_hashes = {c['elf_sha256'] for c in previous['cases']}
    selected, seen = [], set()
    for name in names:
        if name in seen or name in old_names:
            raise ValueError(f'duplicate or previously selected test: {name}')
        seen.add(name)
        test = catalog.tests[name]
        if test.kind != 'rvv' or not test.binary.is_file():
            raise ValueError(f'expected built RVV directed test: {name}')
        digest = batch.sha256(test.binary)
        if digest in old_hashes:
            raise ValueError(f'duplicate ELF, not new stimulus: {name}')
        old_hashes.add(digest)
        selected.append((name, test, digest))
    if not selected:
        raise ValueError('empty extension')
    return selected


def prepare(output, previous, selection):
    state = batch.read(previous / 'checkpoint.json')
    if state['status'] not in ('PASS', 'COMPLETE_WITH_FAILURES') or state['completed'] != state['total']:
        raise ValueError('previous batch must be complete')
    old = batch.frozen(previous, all_cases=True)
    batch.base.sources(Path(old['checkpoint']) / 'sim/vcs_source_manifest.json')
    names = batch.read(selection)['tests']
    catalog = batch.load_catalog(ROOT, ROOT / 'verification/suites.json')
    selected = select_tests(catalog, old, names)
    output.mkdir(parents=True, exist_ok=False)
    # Reuse the project's ELF parser environment; the simulation/checker stays
    # on its existing system Python and does not acquire a new dependency.
    fit_command = [str(ROOT / 'verification/tools/soc-venv/bin/python'),
                   str(HERE / 'check_elf_fit.py'), '--ram-bytes', str(2 * 1024 * 1024),
                   '--output', str(output / 'elf_fit.json')]
    for _, test, _ in selected:
        fit_command += ['--elf', str(test.binary)]
    subprocess.run(fit_command, check=True, timeout=60)
    files = dict(old['files'])
    files.update(batch.pins([SCRIPT, Path(batch.__file__), selection,
                            previous / 'checkpoint.json', previous / 'plan.json',
                            previous / 'plan.sha256.json', HERE / 'check_elf_fit.py']))
    cases, reused = list(old['cases']), []
    for case in cases:
        path = previous / 'outcomes' / (case['name'] + '.json')
        record = batch.read(path)
        batch.check(record['files'])
        if record['vdb_valid'] and batch.base.inventory(Path(record['vdb'])) != record['vdb_files']:
            raise ValueError('prior VDB changed')
        files.update(batch.pins([path]))
        record = dict(record, reused=True)
        batch.save(output / 'outcomes' / path.name, record)
        reused.append(case['name'])
    for key, test, digest in selected:
        name = 'extra-' + re.sub(r'[^A-Za-z0-9_.-]', '-', key)
        elf = output / 'inputs' / (name + '.elf')
        elf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(test.binary, elf)
        batch.check({str(elf): digest})
        source = ROOT / 'apps/riscv-tests/isa/rv64uv' / (key.split(':', 1)[1] + '.c')
        source_files = batch.pins([test.binary, elf, selection] + ([source] if source.is_file() else []))
        cases.append({'name': name, 'kind': 'directed', 'test': key,
                      'source_name': test.name, 'source_audit': None,
                      'oracle': 'selfcheck+trace-audit', 'timeout_s': min(test.timeout_s, 300),
                      'frozen_elf': str(elf), 'elf_sha256': digest,
                      'directed_test': dict(asdict(test), binary=str(elf)),
                      'coverage_test': re.sub(r'[^A-Za-z0-9_]', '_', test.testcase),
                      'source_files': source_files})
    config = output / 'inputs/coverage-wrapper.json'
    batch.save(config, {'simv': old['simv'], 'image': old['image'], 'results': str(output / 'results')})
    wrapper = output / 'inputs/coverage_simv'
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(SCRIPT), '--coverage-exec', str(config)]) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + '.daidir').symlink_to(Path(old['simv'] + '.daidir'), target_is_directory=True)
    shutil.copyfile(Path(old['checkpoint']) / 'sim/simulator.conf', output / 'inputs/simulator.conf')
    files.update(batch.pins([config, wrapper, output / 'inputs/simulator.conf']))
    plan = dict(old, cases=cases, files=files, reused=reused, wrapper=str(wrapper),
                wrapper_image=batch.simulation_image(wrapper),
                source_selection={'previous': str(previous), 'new_directed': names,
                                  'previous_selection': old['source_selection']})
    batch.save(output / 'plan.json', plan)
    batch.save(output / 'plan.sha256.json', batch.pins([output / 'plan.json']))
    batch.frozen(output, all_cases=True)
    batch.save(output / 'checkpoint.json', {'status': 'PREPARED', 'phase': 'coverage extension',
               'total': len(cases), 'workers': 8, 'cases': {}, 'simulations_started': False,
               'source_selection': plan['source_selection']})
    for name in reused:
        batch.publish(output, batch.read(output / 'outcomes' / (name + '.json')))
    print(f'PREPARED: {len(selected)} new, {len(reused)} inherited, no simulation started')


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--coverage-exec':
        argv = batch.adapter_command(batch.read(sys.argv[2]), sys.argv[3:], Path.cwd().resolve())
        with Path('coverage.command.json').open('x') as stream:
            import json
            json.dump({'command': argv, 'cwd': str(Path.cwd())}, stream)
        os.execv(argv[0], argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=8)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--worker')
    modes.add_argument('--directed')
    args = parser.parse_args()
    output = batch.base.checked_output(args.output)
    os.environ['PYTHONPATH'] = str(ROOT / 'verification')
    if args.worker:
        return batch.worker(output, args.worker)
    if args.directed:
        return batch.directed(output, args.directed)
    if args.execute:
        return batch.execute(output, args.jobs)
    if not args.previous or not args.selection:
        parser.error('prepare requires --previous and --selection')
    prepare(output, args.previous.resolve(strict=True), args.selection.resolve(strict=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
