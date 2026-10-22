#!/usr/bin/env python3
"""Run one discriminating Sv39 case before extending same-image PASS coverage."""
import argparse
import copy
import csv
from dataclasses import asdict
import os
from pathlib import Path
import shlex
import shutil
import sys

import run_gap33_20261001 as previous
import vcs_point_audit as point

full = previous.full
SCRIPT = Path(__file__).resolve()
SOURCE = full.ROOT / 'verification/out/gap33-current-20261001-01'
BUILD = full.ROOT / 'verification/out/gap34-build-20261001-01'
BASELINE = full.ROOT / 'verification/out/gap34-baseline-20261001-01/points.json'
NAMES = ['sv39_gap34_' + kind for kind in ('load', 'store', 'fetch')]


def history():
    rows = full.read(previous.SOURCE / 'all-outcomes.json') + full.read(SOURCE / 'all-outcomes.json')
    full.require(len(rows) == 617 and len({r['name'] for r in rows}) == 617, 'baseline membership drift')
    return rows


def prepare(output):
    full.require(not output.exists(), 'independent directory required')
    original = full.frozen(previous.ORIGINAL, all_cases=True)
    collection = full.read(SOURCE / 'collection.json')
    full.require(collection['status'] == 'PASS' and collection['passed'] == collection['total'] == 617,
                 'requires verified 617-case baseline')
    full.require(collection['image'] == original['image'], 'baseline image mismatch')
    full.check(collection['reports'])
    old = previous.admitted(history(), original['simv'])
    baseline = full.read(BASELINE)
    full.require(baseline['tests'] == 617, 'point baseline differs')
    full.require(Path(baseline['inputs']).read_text() ==
                 (SOURCE / 'combined-dve/inputs.txt').read_text(), 'point VDB membership differs')
    spike = full.read(BUILD / 'spike_results.json')
    full.require([r['test'] for r in spike] == ['rvv:' + n for n in NAMES] and
                 all(r['returncode'] == 0 for r in spike), 'Spike precheck incomplete')
    output.mkdir(parents=True)
    plan = copy.deepcopy(original)
    plan.update(cases=[], service='ara-gap34-' + output.name + '.service',
                source_selection={'baseline': str(SOURCE), 'new_tests': NAMES})
    evidence = [BUILD / 'spike_results.json', BUILD / 'build_commands.json', BASELINE,
                Path(baseline['inputs']), SOURCE / 'collection.json', SOURCE / 'all-outcomes.json',
                previous.SOURCE / 'all-outcomes.json',
                full.ROOT / 'verification/tests/build_sv39_gap34.py', Path(point.__file__),
                full.ROOT / 'apps/riscv-tests/isa/rv64uv/sv39_gap34_body.h']
    hashes = {r['elf_sha256'] for r in old}
    for stem in NAMES:
        name = 'gap34-' + stem
        source = full.ROOT / 'apps/riscv-tests/isa/rv64uv' / (stem + '.c')
        elf = full.ROOT / 'apps/bin' / ('rv64uv-ara-' + stem)
        digest = full.base.sha256(elf)
        full.require(digest not in hashes, 'duplicate new ELF')
        hashes.add(digest)
        log = BUILD / (stem + '.spike.log')
        full.require('PASSED:' in log.read_text(), 'missing Spike completion')
        evidence.extend([log, BUILD / (stem + '.spike')])
        frozen = output / 'inputs' / (name + '.elf')
        frozen.parent.mkdir(exist_ok=True)
        shutil.copyfile(elf, frozen)
        test = full.batch.TestCase('rvv:' + stem, 'rvv', 'unused-no-build', frozen, stem, 900)
        case = {'name': name, 'kind': 'directed', 'source_name': test.name,
                'oracle': 'selfcheck+trace-audit', 'source_audit': 'Spike precheck + scalar architectural oracle',
                'timeout_s': 900, 'frozen_elf': str(frozen), 'elf_sha256': digest,
                'coverage_test': stem, 'directed_test': dict(asdict(test), binary=str(frozen)),
                'origins': [{'source': str(source), 'name': stem}],
                'source_files': full.pins([source, elf, frozen, evidence[-1]])}
        case['contract'] = full.contract(case)
        plan['cases'].append(case)
    config = output / 'inputs/coverage-wrapper.json'
    wrapper = output / 'inputs/coverage_simv'
    full.save(config, {'simv': plan['simv'], 'image': plan['image'], 'results': str(output / 'results')})
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(full.SCRIPT),
                       '--coverage-exec', str(config)]) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + '.daidir').symlink_to(Path(plan['simv'] + '.daidir'), target_is_directory=True)
    shutil.copyfile(previous.ORIGINAL / 'inputs/simulator.conf', output / 'inputs/simulator.conf')
    plan.update(wrapper=str(wrapper), wrapper_image=full.batch.simulation_image(wrapper))
    plan['files'].update(full.pins([SCRIPT, Path(previous.__file__), config, wrapper,
        output / 'inputs/simulator.conf', *evidence]))
    full.save(output / 'plan.json', plan)
    full.save(output / 'plan.sha256.json', full.pins([output / 'plan.json']))
    full.save(output / 'checkpoint.json', {'status': 'PREPARED', 'phase': 'Sv39 discriminating gate',
        'total': 3, 'workers': 8, 'cases': {}, 'simulations_started': False,
        'baseline_passed': 617, 'coverage_status': 'PENDING'})
    full.frozen(output, all_cases=True)
    print('READY: load coverage-gain gate, then store/fetch; same frozen VCS image', flush=True)


def schedule(output, names, jobs):
    plan = full.read(output / 'plan.json')
    first = names[0]
    full.save(output / 'coverage-gate.json', {'status': 'RUNNING', 'case': first})
    full.original_schedule(output, [first], 1)
    item = full.read(output / 'outcomes' / (first + '.json'))
    full.require(item['status'] == 'PASS' and item['passed_only'], 'representative correctness gate failed')
    previous.admitted([item], plan['simv'])
    inputs = output / 'representative-inputs.txt'
    inputs.write_text(plan['design_vdb'] + '\n' + item['vdb'] + '\n')
    before = full.read(BASELINE)
    new = point.audit(inputs, before['instances'])
    merged = point.union(before, new)
    delta = point.gains(before, merged)
    count = sum(m['new_points'] for metrics in delta.values() for m in metrics.values())
    full.save(output / 'representative-points.json', new)
    full.save(output / 'coverage-gate.json', {'status': 'PASS' if count else 'NO_COVERAGE_GAIN',
        'case': first, 'new_points': count, 'delta': delta})
    full.require(count > 0, 'no targeted gain: remaining cases NOT dispatched')
    (output / 'scheduler').rename(output / 'representative-scheduler')
    full.original_schedule(output, names[1:], jobs)


def summarize(output, plan):
    outcomes = full.summarize(output, plan)
    shutil.copyfile(output / 'collection.json', output / 'new-collection.json')
    old = previous.admitted(history(), plan['simv'])
    passed = previous.admitted([r for r in outcomes if r['status'] == 'PASS'],
                              plan['simv'], {r['elf_sha256'] for r in old})
    rows = old + passed
    full.require(len({r['name'] for r in rows}) == len(rows), 'duplicate merged result')
    databases = {plan['design_vdb']: plan['design_files'], **{r['vdb']: r['vdb_files'] for r in rows}}
    full.require(len(databases) == len(rows) + 1, 'duplicate merged VDB')
    full.require(all(full.base.inventory(Path(p)) == h for p, h in databases.items()), 'VDB drift before merge')
    inputs = output / 'combined-inputs.txt'
    inputs.write_text('\n'.join(databases) + '\n')
    target = output / 'combined-dve'
    full.require(full.batch.invoke(['bash', str(full.DVE / 'run_dve_coverage.sh'), str(target),
        '--inputs-file', str(inputs)], output / 'logs/combined-dve.log', plan['dve_outer_timeout_s'],
        {'DVE_COVERAGE_TIMEOUT': str(plan['dve_timeout_s']), 'DVE_WAIVERS': 'auto'}) == 0, 'combined DVE failed')
    expected = [str(Path(r['vdb']).with_suffix('') / r['coverage_test']) for r in rows]
    full.require((target / 'selected_tests.txt').read_text().splitlines() == expected, 'DVE test selection drift')
    full.require((target / 'inputs.txt').read_text().splitlines() == list(databases), 'DVE VDB selection drift')
    full.require(all(full.base.inventory(Path(p)) == h for p, h in databases.items()), 'DVE modified VDB')
    before = next(csv.DictReader((SOURCE / 'combined-dve/summary.csv').open()))
    after = next(csv.DictReader((target / 'summary.csv').open()))
    delta = {k: {'before': before[k], 'after': after[k], 'percentage_points':
        round(float(after[k].rstrip('%')) - float(before[k].rstrip('%')), 2)}
        for k in ('Line', 'Toggle', 'FSM', 'Condition', 'Branch')}
    full.save(output / 'coverage-delta.json', delta)
    baseline = full.read(BASELINE)
    fresh = point.audit(output / 'dve-inputs.txt', baseline['instances'])
    merged = point.union(baseline, fresh)
    full.save(output / 'combined-points.json', merged)
    full.save(output / 'point-delta.json', point.gains(baseline, merged))
    full.save(output / 'collection.json', {'status': 'PASS' if len(passed) == 3 else 'COMPLETE_WITH_FAILURES',
        'total': 620, 'passed': len(rows), 'new_passed': len(passed), 'baseline_passed': 617,
        'image': plan['image'], 'cross_image_reuse': False,
        'excluded': [r['name'] for r in outcomes if r['status'] != 'PASS'],
        'reports': full.pins([target / 'summary.csv', target / 'selected_tests.txt', target / 'inputs.txt',
            target / 'waiver_status.json', output / 'coverage-delta.json', output / 'point-delta.json'])})
    return outcomes


def main():
    full.batch.SCRIPT = SCRIPT
    full.batch.frozen, full.batch.commands = full.frozen, full.commands
    full.batch.summarize, full.batch.schedule = summarize, schedule
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker')
    parser.add_argument('--directed')
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    output = full.base.checked_output(args.output)
    os.environ['PYTHONPATH'] = str(full.ROOT / 'verification')
    if args.prepare:
        prepare(output)
        return 0
    plan = full.frozen(output)
    if args.launch:
        import subprocess
        command = full.systemd_command(output, plan)
        command[command.index(str(full.SCRIPT))] = str(SCRIPT)
        return subprocess.call(command)
    full.require(os.environ.get('ARA_CHECKPOINT_UNIT') == plan['service'] and os.environ.get('INVOCATION_ID'),
                 'registered systemd service required')
    if args.worker:
        return full.worker(output, args.worker)
    if args.directed:
        return full.batch.directed(output, args.directed)
    full.require(args.execute, '--prepare, --launch or --execute required')
    return full.execute(output)


if __name__ == '__main__':
    raise SystemExit(main())
