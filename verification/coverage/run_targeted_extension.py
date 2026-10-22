#!/usr/bin/env python3
"""Extend an audited same-image corpus with coverage-directed, checked cases."""
import argparse
from collections import Counter
import copy
import csv
from dataclasses import asdict
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import run_full_recollection_20260928 as full
import run_gap33_20261001 as admission
import coverage_bitmap_delta as bitmaps

SCRIPT = Path(__file__).resolve()
ORIGINAL = admission.ORIGINAL


def ledger(directory, seen=None):
    directory = directory.resolve(strict=True)
    seen = set() if seen is None else seen
    full.require(directory not in seen, 'cyclic baseline chain')
    seen.add(directory)
    collection = full.read(directory / 'collection.json')
    full.require(collection['status'] in ('PASS', 'COMPLETE_WITH_FAILURES'), 'unfinished baseline')
    full.check(collection['reports'])
    saved = directory / 'all-passed-outcomes.json'
    if saved.exists():
        full.require(str(saved) in collection['reports'], 'unbound baseline ledger')
        rows = full.read(saved)
    else:
        rows = [r for r in full.read(directory / 'all-outcomes.json') if r['status'] == 'PASS']
        if len(rows) != collection['passed']:
            prior = full.read(directory / 'plan.json')['source_selection']['baseline']
            rows = ledger(Path(prior), seen) + rows
    full.require(len(rows) == collection['passed'], 'baseline count differs')
    full.require(len({r['name'] for r in rows}) == len(rows), 'duplicate baseline names')
    return rows


def prepare(output, selection):
    full.require(not output.exists(), 'new output directory required')
    spec = full.read(selection)
    prior = full.absolute(spec['baseline']).resolve(strict=True)
    original = full.frozen(ORIGINAL, all_cases=True)
    collection = full.read(prior / 'collection.json')
    full.require(collection['image'] == original['image'], 'baseline image differs')
    rows = admission.admitted(ledger(prior), original['simv'])
    inputs = prior / 'combined-dve/inputs.txt'
    full.require(inputs.read_text().splitlines() == [original['design_vdb'], *[r['vdb'] for r in rows]],
                 'baseline DVE membership differs')
    bitmap_path = full.absolute(spec['baseline_bits']).resolve(strict=True)
    baseline_bits = full.read(bitmap_path)
    full.require(baseline_bits['tests'] == [r['vdb'] for r in rows], 'baseline bitmap membership differs')
    full.check(baseline_bits['input_hashes'])
    output.mkdir(parents=True)
    plan = copy.deepcopy(original)
    plan.update(cases=[], service='ara-coverage-' + output.name + '.service',
        baseline=str(prior), baseline_bits=str(bitmap_path), baseline_passed=len(rows),
        source_selection={'baseline': str(prior), 'selection': str(selection)})
    sources = [SCRIPT, Path(bitmaps.__file__), Path(admission.__file__), selection, bitmap_path,
               prior / 'collection.json', inputs]
    hashes = {r['elf_sha256'] for r in rows}
    seen, stems = set(), {r['name'] for r in rows}
    for item in spec['cases']:
        name = item['name']
        full.require(re.fullmatch(r'(rvv|app):[A-Za-z0-9_]+', name) and name not in seen, 'invalid/duplicate name')
        seen.add(name)
        kind, stem = name.split(':')
        full.require(stem not in stems, 'duplicate worker/result label')
        stems.add(stem)
        full.require(item.get('rationale') and item.get('targets'), 'missing coverage rationale/targets')
        for target in item['targets']:
            full.require(target.startswith('ara_tb.dut.i_ara_soc.i_system.') and any(
                n == target or n.startswith(target + '.') for metric in baseline_bits['metrics'].values()
                for n in metric), 'coverage target outside measured product hierarchy')
        full.require(0 < item['timeout_s'] <= 1800, 'bounded short case required')
        evidence = [full.absolute(p).resolve(strict=True) for p in item['evidence']]
        source_files = [full.absolute(p).resolve(strict=True) for p in item['sources']]
        full.require(evidence and source_files, 'precheck and source evidence required')
        sources.extend(evidence)
        elf = full.absolute(item['binary']).resolve(strict=True)
        digest = full.base.sha256(elf)
        full.require(digest not in hashes, 'ELF already covered or duplicated')
        hashes.add(digest)
        frozen = output / 'inputs' / (stem + '.elf')
        frozen.parent.mkdir(exist_ok=True)
        shutil.copyfile(elf, frozen)
        test = full.batch.TestCase(name, kind, 'unused-no-build', frozen, stem, item['timeout_s'])
        case = {'name': stem, 'kind': 'directed', 'source_name': name,
            'oracle': 'selfcheck+trace-audit', 'source_audit': item['source_audit'],
            'timeout_s': item['timeout_s'], 'frozen_elf': str(frozen), 'elf_sha256': digest,
            'coverage_test': stem, 'directed_test': dict(asdict(test), binary=str(frozen)),
            'origins': [{'source': str(selection), 'name': name}],
            'source_files': full.pins([elf, frozen, *source_files]),
            'coverage_targets': item['targets'], 'coverage_rationale': item['rationale']}
        case['contract'] = full.contract(case)
        plan['cases'].append(case)
    full.require(plan['cases'], 'empty extension')
    baseline_ledger = output / 'inputs/baseline-ledger.json'
    full.save(baseline_ledger, rows)
    config = output / 'inputs/coverage-wrapper.json'
    wrapper = output / 'inputs/coverage_simv'
    full.save(config, {'simv': plan['simv'], 'image': plan['image'], 'results': str(output / 'results')})
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(full.SCRIPT),
        '--coverage-exec', str(config)]) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + '.daidir').symlink_to(plan['simv'] + '.daidir', target_is_directory=True)
    shutil.copyfile(ORIGINAL / 'inputs/simulator.conf', output / 'inputs/simulator.conf')
    plan.update(wrapper=str(wrapper), wrapper_image=full.batch.simulation_image(wrapper))
    plan['files'].update(full.pins([*sources, baseline_ledger, config, wrapper, output / 'inputs/simulator.conf']))
    full.save(output / 'plan.json', plan)
    full.save(output / 'plan.sha256.json', full.pins([output / 'plan.json']))
    full.save(output / 'checkpoint.json', {'status': 'PREPARED', 'phase': 'targeted extension',
        'total': len(plan['cases']), 'workers': 8, 'cases': {}, 'simulations_started': False,
        'baseline_passed': len(rows), 'coverage_status': 'PENDING'})
    full.frozen(output, all_cases=True)
    print(f'PREPARED: {len(plan["cases"])} new cases, {len(rows)} baseline PASS', flush=True)


def hierarchy_rows(path):
    result, stack = {}, []
    with path.open() as stream:
        for row in csv.DictReader(stream):
            depth = int(row['Depth'])
            stack = stack[:depth]
            full.require(len(stack) == depth, 'missing DVE hierarchy parent')
            stack.append(row['Name'])
            name = '.'.join(stack)
            full.require(name not in result, 'duplicate DVE hierarchy')
            result[name] = row
    return result


def summarize(output, plan):
    outcomes = []
    for case in plan['cases']:
        item = full.read(output / 'outcomes' / (case['name'] + '.json'))
        full.require(item['name'] == case['name'] and item['contract'] == case['contract'] and
                     item['elf_sha256'] == case['elf_sha256'], 'outcome contract differs')
        full.check(item['files'])
        full.require(Path(item['vdb']).is_relative_to(output / 'results' / case['name']), 'foreign new VDB')
        if item['status'] == 'PASS':
            full.require(item['passed_only'] and item['vdb_valid'] and not item['reused'], 'unverified PASS')
            full.require(full.batch.valid_vdb(Path(item['vdb']), item['coverage_test'], plan['simv']) ==
                         item['vdb_files'], 'new VDB drift')
        else:
            full.require(not item['passed_only'], 'failed test admitted')
        outcomes.append(item)
    full.save(output / 'all-outcomes.json', outcomes)
    old = full.read(output / 'inputs/baseline-ledger.json')
    passed = [r for r in outcomes if r['status'] == 'PASS']
    rows = old + passed
    full.require(len({r['name'] for r in rows}) == len(rows), 'duplicate merged names')
    databases = {plan['design_vdb']: plan['design_files'], **{r['vdb']: r['vdb_files'] for r in rows}}
    full.require(len(databases) == len(rows) + 1, 'duplicate merged VDB')
    full.require(all(full.base.inventory(Path(p)) == h for p, h in databases.items()), 'VDB drift before DVE')
    inputs = output / 'combined-inputs.txt'
    inputs.write_text('\n'.join(databases) + '\n')
    target = output / 'combined-dve'
    full.require(full.batch.invoke(['bash', str(full.DVE / 'run_dve_coverage.sh'), str(target),
        '--inputs-file', str(inputs)], output / 'logs/combined-dve.log', plan['dve_outer_timeout_s'],
        {'DVE_COVERAGE_TIMEOUT': str(plan['dve_timeout_s']), 'DVE_WAIVERS': 'auto'}) == 0, 'DVE failed')
    full.require((target / 'inputs.txt').read_text().splitlines() == list(databases), 'DVE input set differs')
    expected = [str(Path(r['vdb']).with_suffix('') / r['coverage_test']) for r in rows]
    full.require((target / 'selected_tests.txt').read_text().splitlines() == expected, 'DVE selected tests differ')
    full.require(all(full.base.inventory(Path(p)) == h for p, h in databases.items()), 'DVE changed input VDB')
    before = hierarchy_rows(Path(plan['baseline']) / 'combined-dve/summary.csv')
    after = hierarchy_rows(target / 'summary.csv')
    full.require(before.keys() == after.keys(), 'DVE hierarchy changed')
    official = {}
    for name in after:
        changes = {}
        for metric in ('Line', 'Toggle', 'FSM', 'Condition', 'Branch'):
            a, b = before[name][metric], after[name][metric]
            if a == b:
                continue
            full.require(a != 'NA' and b != 'NA', 'DVE denominator changed')
            diff = round(float(b.rstrip('%')) - float(a.rstrip('%')), 2)
            full.require(diff >= 0, 'DVE cumulative coverage decreased')
            changes[metric] = {'before': a, 'after': b, 'percentage_points': diff}
        if changes:
            official[name] = changes
    full.save(output / 'coverage-delta.json', official)
    baseline_bits = full.read(Path(plan['baseline_bits']))
    merged = baseline_bits
    per_case = []
    for row in passed:
        listing = output / 'inputs' / (row['name'] + '.vdbs.txt')
        listing.write_text(plan['design_vdb'] + '\n' + row['vdb'] + '\n')
        fresh = bitmaps.collect(listing)
        prior = merged
        merged = bitmaps.combine(merged, fresh)
        gains = bitmaps.delta(prior, merged)
        case = next(c for c in plan['cases'] if c['name'] == row['name'])
        matched = [r for r in gains['instances'] if any(
            r['instance'] == t or r['instance'].startswith(t + '.') for t in case['coverage_targets'])]
        per_case.append({'name': row['name'], 'new_bits': gains['metrics'], 'target_gains': matched,
                         'all_gains': gains['instances']})
    full.save(output / 'per-case-gains.json', per_case)
    full.save(output / 'combined-bits.json', merged)
    full.save(output / 'raw-bitmap-delta.json', bitmaps.delta(baseline_bits, merged))
    full.save(output / 'all-passed-outcomes.json', rows)
    reports = [target / n for n in ('summary.csv', 'selected_tests.txt', 'inputs.txt', 'waiver_status.json')]
    reports += [output / n for n in ('all-passed-outcomes.json', 'coverage-delta.json',
        'per-case-gains.json', 'combined-bits.json', 'raw-bitmap-delta.json')]
    full.save(output / 'collection.json', {'status': 'PASS' if len(passed) == len(outcomes) else 'COMPLETE_WITH_FAILURES',
        'total': len(old) + len(outcomes), 'passed': len(rows), 'baseline_passed': len(old),
        'new_passed': len(passed), 'image': plan['image'], 'cross_image_reuse': False,
        'counts': dict(Counter(r['status'] for r in outcomes)),
        'excluded': [r['name'] for r in outcomes if r['status'] != 'PASS'], 'reports': full.pins(reports)})
    return outcomes


def execute(output):
    rc = full.execute(output)
    state = full.read(output / 'checkpoint.json')
    if state['phase'] == 'complete':
        collection = full.read(output / 'collection.json')
        full.check(collection['reports'])
        state.update(coverage_status='COMPLETE', aggregate_passed=collection['passed'])
        full.save(output / 'checkpoint.json', state)
    return rc


def main():
    full.batch.SCRIPT, full.batch.frozen = SCRIPT, full.frozen
    full.batch.commands, full.batch.summarize = full.commands, summarize
    full.batch.schedule = full.original_schedule
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker')
    parser.add_argument('--directed')
    args = parser.parse_args()
    output = full.base.checked_output(args.output)
    os.environ['PYTHONPATH'] = str(full.ROOT / 'verification')
    if args.prepare:
        full.require(args.selection is not None, '--selection required')
        prepare(output, args.selection.resolve(strict=True))
        return 0
    plan = full.frozen(output)
    if args.launch:
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
    return execute(output)


if __name__ == '__main__':
    raise SystemExit(main())
