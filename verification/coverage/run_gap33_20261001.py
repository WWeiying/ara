#!/usr/bin/env python3
"""Same-image gap extension; admit only independently audited PASS databases."""
import argparse
import copy
import csv
from dataclasses import asdict
import os
from pathlib import Path
import shlex
import shutil
import sys

import run_full_recollection_20260928 as full

SCRIPT = Path(__file__).resolve()
SOURCE = full.ROOT / 'verification/out/repaired-timeout-closure-20260930-01'
ORIGINAL = full.ROOT / 'verification/out/repaired-aligned-600-20260930-01'
BUILD = full.ROOT / 'verification/out/gap33-build-20261001-01'
CSR_BUILD = full.ROOT / 'verification/out/gap33-csr-build-20261001-01'
NAMES = [f'vcoverage_gap33_e{s}_m{m}' for s in (8, 16, 32, 64) for m in (1, 2, 4, 8)] + ['linux_csr_gap33']


def admitted(rows, image, old_hashes=()):
    names, databases, hashes = set(), set(), set(old_hashes)
    for row in rows:
        full.require(row['name'] not in names and row['vdb'] not in databases, 'duplicate result or VDB')
        full.require(row['status'] == 'PASS' and row['passed_only'] and row['vdb_valid'], 'unverified result')
        full.require(row['elf_sha256'] not in hashes, 'duplicate new ELF')
        full.require(full.batch.valid_vdb(Path(row['vdb']), row['coverage_test'], image) == row['vdb_files'], 'VDB drift')
        names.add(row['name']); databases.add(row['vdb'])
        # Historical suite legitimately includes distinct oracle contracts for an ELF.
        if old_hashes:
            hashes.add(row['elf_sha256'])
    return rows


def prepare(output):
    full.require(not output.exists(), 'independent new directory required')
    original = full.frozen(ORIGINAL, all_cases=True)
    collection = full.read(SOURCE / 'collection.json')
    full.require(collection['status'] == 'PASS' and collection['passed'] == collection['total'] == 600,
                 'requires verified 600-case baseline')
    full.require(collection['image'] == original['image'], 'baseline image mismatch')
    full.check(collection['reports'])
    old = full.read(SOURCE / 'all-outcomes.json')
    full.require(len(old) == 600, 'baseline membership differs')
    admitted(old, original['simv'])
    full.require({r['name'] for r in old} == {c['name'] for c in original['cases']}, 'baseline case membership drift')
    evidence = []
    for build, names in ((BUILD, NAMES[:-1]), (CSR_BUILD, NAMES[-1:])):
        rows = full.read(build / 'spike_results.json')
        full.require([r['test'] for r in rows] == ['rvv:' + n for n in names] and
                     all(r['returncode'] == 0 for r in rows), 'Spike precheck incomplete')
        evidence.extend([build / 'spike_results.json', build / 'build_commands.json'])
        for name in names:
            log = build / (name + '.spike.log')
            full.require('PASSED:' in log.read_text(), 'missing Spike completion marker')
            evidence.extend([log, build / (name + '.spike')])
    output.mkdir(parents=True)
    plan = copy.deepcopy(original)
    plan.update(cases=[], service='ara-gap33-' + output.name + '.service',
                source_selection={'baseline': str(SOURCE), 'new_tests': NAMES})
    old_hashes = {c['elf_sha256'] for c in original['cases']}
    for stem in NAMES:
        name = 'gap33-' + stem
        source = full.ROOT / 'apps/riscv-tests/isa/rv64uv' / (stem + '.c')
        elf = full.ROOT / 'apps/bin' / ('rv64uv-ara-' + stem)
        digest = full.base.sha256(elf)
        full.require(digest not in old_hashes, 'ELF already represented')
        old_hashes.add(digest)
        frozen = output / 'inputs' / (name + '.elf')
        frozen.parent.mkdir(exist_ok=True)
        shutil.copyfile(elf, frozen)
        test = full.batch.TestCase('rvv:' + stem, 'rvv', 'unused-no-build', frozen, stem, 900)
        case = {'name': name, 'kind': 'directed', 'source_name': test.name,
                'oracle': 'selfcheck+trace-audit', 'source_audit': 'Spike precheck + independent scalar oracle',
                'timeout_s': 900, 'frozen_elf': str(frozen), 'elf_sha256': digest,
                'coverage_test': stem, 'directed_test': dict(asdict(test), binary=str(frozen)),
                'origins': [{'source': str(source), 'name': stem}],
                'source_files': full.pins([source, elf, frozen,
                    full.ROOT / 'apps/riscv-tests/isa/rv64uv/vcoverage_gap33_body.h'])}
        case['contract'] = full.contract(case)
        plan['cases'].append(case)
    config = output / 'inputs/coverage-wrapper.json'
    wrapper = output / 'inputs/coverage_simv'
    full.save(config, {'simv': plan['simv'], 'image': plan['image'], 'results': str(output / 'results')})
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(full.SCRIPT),
                       '--coverage-exec', str(config)]) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + '.daidir').symlink_to(Path(plan['simv'] + '.daidir'), target_is_directory=True)
    shutil.copyfile(ORIGINAL / 'inputs/simulator.conf', output / 'inputs/simulator.conf')
    plan.update(wrapper=str(wrapper), wrapper_image=full.batch.simulation_image(wrapper))
    plan['files'].update(full.pins([SCRIPT, config, wrapper, output / 'inputs/simulator.conf',
        SOURCE / 'collection.json', SOURCE / 'all-outcomes.json', SOURCE / 'dve-inputs.after.json',
        full.ROOT / 'verification/tests/build_rvv_gap33.py', *evidence]))
    full.save(output / 'plan.json', plan)
    full.save(output / 'plan.sha256.json', full.pins([output / 'plan.json']))
    full.save(output / 'checkpoint.json', {'status': 'PREPARED', 'phase': 'gap33 extension',
        'total': len(NAMES), 'workers': 8, 'cases': {}, 'simulations_started': False,
        'baseline_passed': 600, 'coverage_status': 'PENDING'})
    full.frozen(output, all_cases=True)
    print('READY: 17 new cases, unchanged VCS image, 600 baseline PASS retained')


def summarize(output, plan):
    # The established full-suite merger validates each fresh result and oracle.
    outcomes = full.summarize(output, plan)
    shutil.copyfile(output / 'collection.json', output / 'new-collection.json')
    old = full.read(SOURCE / 'all-outcomes.json')
    passed = [r for r in outcomes if r['status'] == 'PASS']
    admitted(old, plan['simv'])
    admitted(passed, plan['simv'], {r['elf_sha256'] for r in old})
    rows = old + passed
    full.require(len({r['name'] for r in rows}) == len(rows), 'duplicate merged case')
    databases = {plan['design_vdb']: plan['design_files'], **{r['vdb']: r['vdb_files'] for r in rows}}
    full.require(len(databases) == len(rows) + 1, 'duplicate merged VDB')
    full.require(all(full.base.inventory(Path(p)) == h for p, h in databases.items()), 'database changed before merge')
    inputs = output / 'combined-inputs.txt'
    inputs.write_text('\n'.join(databases) + '\n')
    target = output / 'combined-dve'
    full.require(full.batch.invoke(['bash', str(full.DVE / 'run_dve_coverage.sh'), str(target),
        '--inputs-file', str(inputs)], output / 'logs/combined-dve.log', plan['dve_outer_timeout_s'],
        {'DVE_COVERAGE_TIMEOUT': str(plan['dve_timeout_s']), 'DVE_WAIVERS': 'auto'}) == 0, 'combined DVE failed')
    expected = [str(Path(r['vdb']).with_suffix('') / r['coverage_test']) for r in rows]
    full.require((target / 'selected_tests.txt').read_text().splitlines() == expected, 'DVE selected wrong tests')
    full.require((target / 'inputs.txt').read_text().splitlines() == list(databases), 'DVE selected wrong VDBs')
    full.require(all(full.base.inventory(Path(p)) == h for p, h in databases.items()), 'DVE modified input database')
    before = next(csv.DictReader((SOURCE / 'dve/summary.csv').open()))
    after = next(csv.DictReader((target / 'summary.csv').open()))
    delta = {}
    for k in ('Line', 'Toggle', 'FSM', 'Condition', 'Branch'):
        delta[k] = {'before': before[k], 'after': after[k],
                    'percentage_points': round(float(after[k].rstrip('%')) - float(before[k].rstrip('%')), 2)}
    full.save(output / 'coverage-delta.json', delta)
    full.save(output / 'collection.json', {'status': 'PASS' if len(passed) == len(outcomes) else 'COMPLETE_WITH_FAILURES',
        'total': 600 + len(outcomes), 'passed': len(rows), 'new_passed': len(passed),
        'baseline_passed': 600, 'image': plan['image'], 'cross_image_reuse': False,
        'excluded': [r['name'] for r in outcomes if r['status'] != 'PASS'],
        'reports': full.pins([target / 'summary.csv', target / 'selected_tests.txt',
            target / 'waiver_status.json', output / 'coverage-delta.json'])})
    return outcomes


def main():
    full.batch.SCRIPT = SCRIPT
    full.batch.frozen = full.frozen
    full.batch.commands = full.commands
    full.batch.summarize = summarize
    full.batch.schedule = full.original_schedule
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker')
    parser.add_argument('--directed')
    args = parser.parse_args()
    output = full.base.checked_output(args.output)
    os.environ['PYTHONPATH'] = str(full.ROOT / 'verification')
    if args.prepare:
        prepare(output)
        return 0
    plan = full.frozen(output)
    full.require(os.environ.get('ARA_CHECKPOINT_UNIT') == plan['service'] and os.environ.get('INVOCATION_ID'),
                 'registered systemd service required')
    if args.worker:
        return full.worker(output, args.worker)
    if args.directed:
        return full.batch.directed(output, args.directed)
    full.require(args.execute, '--prepare or --execute required')
    return full.execute(output)


if __name__ == '__main__':
    raise SystemExit(main())
