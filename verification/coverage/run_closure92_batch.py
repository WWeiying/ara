#!/usr/bin/env python3
"""Checked successor of closure90; no implicit compose, launch, or EDA mocks.

New adapters: --adapter 71=run_gap71_<subject>_checked_extension (also 72/73).
Each exports CASE_NAMES/NAMES (a strict identity list), or legacy NAME/audit.NAME,
install_hooks(), and
runtime_proof(output, plan, row, proof). The latter must actually replay its
oracle and return {status: PASS, schema: ..., files: bound runtime SHA map, ...}.
Multi-case results also return name=<full identity>. The map includes this
case's stdout, commit trace, ELF, and vector trace (empty events are permitted
only when its own oracle accepts them). Selected subsets total at most eight.
Only hash aliases are cached, and no success is published before final rehash.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import run_closure90_batch as predecessor
import compose_repair_selection as composer
import coverage_evidence as evidence
import coverage_hash_session as hashes
import run_checked_extension as checked
from ara_verify import plan as run_audit
from ara_verify.trace import validate_trace

ROOT = predecessor.ROOT
SCRIPT = Path(__file__).resolve()
BASELINE = ROOT / 'verification/out/closure90-current-20261005-01'
HISTORY = predecessor.BASELINE
COMPLETION = predecessor.COMPLETION
SCHEMA = 'closure92-batch-v1'
TRACE_PLUSARGS = {
    'gap71_qbs_read': ('+QBS_PERF',),
    'gap71_qbs_fault': ('+QBS_PERF',),
    'gap71_akv_read': ('+AKV_PERF',),
    'gap71_akv_fault': ('+AKV_PERF',),
    'qbs_gap72_fill_abort': ('+QBS_PERF',),
    'akv_gap72_tile_range': ('+AKV_PERF',),
    'akv_gap73_v1_onehot': ('+AKV_PERF',),
}
# Captured only after the main thread declared this exact 654 tip COMPLETE.
# Plan binds producer/source pins; collection binds all published DVE/bitmaps.
BASELINE_IDENTITY = {
    'checkpoint.json': '6306ddb1c4baa282b55a7588f8f2dcbcacbea45357daecfe1d5fcdad773bab88',
    'plan.json': '7dba67ac552e0f0a65fa1df6f8f6e8ec2e3469da738ca88e9ee965e33a9ecf49',
    'plan.sha256.json': 'cf8e4bca380a41172a4ebf904c0453d3de41b57ebd6f2291c0101a534f9b7139',
    'collection.json': '96c65e4344f75fcc44eb1286e6872285fad759e8143d692ae4c6867b19f5aef4',
    'all-outcomes.json': 'c62331b28b7da432dc82308473e7c83265d63889ffe2e67f8b894997eadfd0c7',
    'checked-preflight.json': 'f521c4be8a91f64d0057fd774c1f5499f8a37ec827cbb08dc9210835a0d7aa73',
    'prepare-hash-session.json': 'd43b25ab4ec5e532dccbc5526c8e8cca546b9a482d2dad8471a8f8988f992783',
    'summarize-hash-session.json': '1c1a5c648a11e0051b24e230ea52779d2d4a233a031e7f47f77b9bf9a21539a6',
    'results/sv39_gap68_warm_permissions_pmp0/run.json':
        '43346a863c2d7db9af4749abfa701696d751680d2c979b14df9ddb618ee7e4eb',
    'results/vgap69_vf_odd_vd/run.json':
        '6b6331d262c5615643c36db805a00d21df10879704837c4ccd16e3e472cebbcf',
    'results/vgap70_indexed_fault_recover/run.json':
        '0720022054ead9ed9124731a8a139dacad4517968489ba9b473eedcb58cf98ff',
}
require = evidence.require
_installed = None


def completion_gate(proof):
    state = proof.read(BASELINE / 'checkpoint.json')
    require(state.get('coverage_status') == 'COMPLETE' and
            state.get('status') == 'PASS' and state.get('phase') == 'complete' and
            state.get('aggregate_passed') == 654, 'checked654 is not COMPLETE')
    return state


def adapter_name(module):
    return getattr(module, 'NAME', getattr(getattr(module, 'audit', None), 'NAME', None))


def adapter_names(module):
    declarations = [getattr(module, key) for key in ('CASE_NAMES', 'NAMES') if hasattr(module, key)]
    if not declarations:
        declarations = [[adapter_name(module)]]
    names = declarations[0]
    require(type(names) is list and 0 < len(names) <= 8 and
            all(isinstance(n, str) and re.fullmatch(r'(rvv|app):[A-Za-z0-9_]+', n) for n in names) and
            len(set(names)) == len(names) and all(value == names for value in declarations),
            'invalid/ambiguous adapter identity list')
    return names


def unique_modules(modules):
    return list({str(Path(m.__file__).resolve()): m for m in modules.values()}.values())


def load_adapters(bindings):
    require(isinstance(bindings, dict) and 0 < len(bindings) <= 3 and
            set(bindings) <= {'71', '72', '73'}, 'only gap71/72/73 adapters allowed')
    modules = {}
    for gap, name in sorted(bindings.items()):
        require(isinstance(name, str) and re.fullmatch(
            'run_gap' + gap + r'_[a-z0-9_]+_checked_extension', name), 'foreign adapter module')
        module = importlib.import_module(name)
        require(Path(module.__file__).resolve() == SCRIPT.parent / (name + '.py'),
                'foreign adapter source')
        require(callable(getattr(module, 'install_hooks', None)) and
                callable(getattr(module, 'runtime_proof', None)), 'missing strict runtime adapter API')
        for case in adapter_names(module):
            require(re.search(r'gap' + gap + r'(?:_|$)', case.split(':')[1]), 'foreign adapter case')
            require(case.split(':')[1] not in {n.split(':')[1] for n in modules}, 'duplicate adapter case')
            modules[case] = module
    return modules


def runtime_inputs(output, row, proof, source_name):
    target = output / 'results' / source_name.split(':')[1]
    require(row['name'] == target.name, 'foreign runtime row')
    summary_path = target / 'summary.json'
    require(str(summary_path) in row['files'], 'unbound runtime summary')
    proof.pin(summary_path, row['files'][str(summary_path)])
    summaries = proof.read(summary_path)
    require(len(summaries) == 1 and summaries[0]['name'] == source_name, 'runtime summary identity differs')
    artifact = Path(summaries[0]['artifact_dir']).resolve(strict=True)
    require(artifact.is_relative_to(target.resolve()), 'foreign runtime artifact')
    paths = [summary_path, artifact / 'work/run.vcs.log', artifact / 'commit_trace.csv',
             artifact / 'input.elf']
    for path in paths:
        require(str(path) in row['files'], 'unbound runtime input: ' + str(path))
        proof.pin(path, row['files'][str(path)])
    return target, artifact, paths


def audit_runtime(module, output, plan, row, proof):
    declared = adapter_names(module)
    matches = [n for n in declared if n.split(':')[1] == row.get('name')]
    require(len(matches) == 1, 'runtime row not a unique declared adapter case')
    name = matches[0]
    cases = [c for c in plan['cases'] if c['name'] == row['name']]
    require(len(cases) == 1 and cases[0]['source_name'] == name, 'runtime producer case differs')
    target, artifact, paths = runtime_inputs(output, row, proof, name)
    vector = artifact / 'work/vector_trace.csv'
    require(str(vector) in row['files'], 'unbound runtime vector trace')
    proof.pin(vector, row['files'][str(vector)])
    proof.pin(paths[-1], cases[0]['elf_sha256'])
    result = module.runtime_proof(output, plan, row, proof)
    require(isinstance(result, dict) and result.get('status') == 'PASS' and
            isinstance(result.get('schema'), str) and result['schema'] and
            isinstance(result.get('files'), dict) and
            set(map(str, [*paths[1:], vector])) <= set(result['files']) and
            bool(set(result) - {'status', 'schema', 'files'}), 'runtime audit lacks replay evidence')
    require(len(declared) == 1 or result.get('name') == name,
            'multi-case runtime audit must identify this exact case')
    def bound_runtime_file(path, digest):
        runtime = (row['files'].get(path) == digest and
                   Path(path).resolve().is_relative_to(target.resolve()))
        database = (row.get('vdb_files', {}).get(path) == digest and
                    Path(path).resolve().is_relative_to(Path(row['vdb']).resolve()))
        return (runtime or database) and proof.files.get(path) == digest

    require(all(bound_runtime_file(p, h) for p, h in result['files'].items()),
            'runtime audit uses unbound/unchecked bytes')
    proof.hashes(result['files'])
    return result


def old_runtime(module, output, plan, row, proof):
    # Gap68/70 sealed helpers have no custom VCS hook. Re-run the original
    # complete/trace admission, then their exact selfcheck oracle on actual RTL.
    name = adapter_name(module)
    target, artifact, _ = runtime_inputs(output, row, proof, name)
    proof.pin(Path(run_audit.__file__))
    for path in target.rglob('*'):
        if path.is_file() and path.suffix == '.json':
            if path == target / 'run.json':
                proof.pin(path, BASELINE_IDENTITY[str(path.relative_to(BASELINE))])
            else:
                require(str(path) in row['files'], 'unbound runtime audit metadata: ' + str(path))
                proof.pin(path, row['files'][str(path)])
    case = next(c for c in plan['cases'] if c['source_name'] == name)
    checked.full.batch.audit_ok(run_audit.audit_run(target, require_trace=True), case, artifact)
    require(proof.read(artifact / 'trace_summary.json') ==
            dict(status='VALID', **validate_trace(artifact / 'commit_trace.csv')),
            'actual runtime commit trace replay differs')
    source = str(ROOT / 'apps/riscv-tests/isa/rv64uv' / (name.split(':')[1] + '.c'))
    module.audit.check_log((artifact / 'work/run.vcs.log').read_text(), source)


def install(bindings):
    global _installed
    if _installed is not None:
        require(_installed == bindings, 'cannot replace installed adapter chain')
        return load_adapters(bindings)
    modules = load_adapters(bindings)
    predecessor.gap65.install_hooks()
    for name in predecessor.CATALOG.values():
        importlib.import_module(name).install_hooks()
    for module in unique_modules(modules):
        module.install_hooks()
    prior_row = evidence.Evidence.baseline_row

    def chained(proof, row, image, simv):
        result = prior_row(proof, row, image, simv)
        matches = [m for n, m in modules.items() if n.split(':')[1] == row.get('name')]
        if matches:
            target = next(p for p in Path(row['vdb']).parents
                          if p.parent.name == 'results' and p.name == row['name'])
            output = target.parent.parent
            audit_runtime(matches[0], output, proof.plan(output), row, proof)
        return result

    evidence.Evidence.baseline_row = chained
    _installed = dict(bindings)
    return modules


def completed(proof):
    state = completion_gate(proof)
    proof.hashes({str(BASELINE / n): h for n, h in BASELINE_IDENTITY.items()})
    predecessor.completed(proof)
    receipt = proof.read(COMPLETION / 'completion.json')
    proof.hashes(receipt['files'])
    plan = proof.plan(BASELINE)
    require(plan.get('checked_extension') == checked.VERSION and
            plan['source_selection']['baseline'] == str(HISTORY) and
            plan['baseline'] == str(HISTORY) and plan['baseline_passed'] == 651 and
            plan['workers_max'] == 8, 'foreign checked654 sourceplan')
    proof.hashes(plan['files'])
    selection = plan['source_selection']['selection']
    require(selection in plan['files'], 'unbound predecessor selection')
    source = proof.read(selection)
    predecessor.check_selection(source, proof)
    for path in (predecessor.SCRIPT, SCRIPT.parent / 'coverage_hash_session.py',
                 *[SCRIPT.parent / (n + '.py') for n in predecessor.CATALOG.values()]):
        require(str(path) in plan['files'], 'unbound predecessor adapter/runner source')
    collection = proof.collection(BASELINE, plan['image'])
    require(collection['status'] == 'PASS' and collection['passed'] == collection['total'] == 654 and
            collection['baseline_passed'] == 651 and collection['new_passed'] == 3 and
            collection['counts'] == {'PASS': 3} and collection['excluded'] == [] and
            collection['cross_image_reuse'] is False, 'incomplete checked654 collection')
    rows = proof.ledger(BASELINE, plan['image'])
    old = proof.ledger(HISTORY, plan['image'])
    original650 = proof.ledger(predecessor.gap65.BASELINE, plan['image'])
    require(len(original650) == 650 and old == original650 + [old[-1]] and
            old[-1]['name'] == predecessor.gap65.ROW and
            old[-1]['kind'] == 'gap65-observed-v1', 'independent650/gap65 identity differs')
    outcomes = proof.read(BASELINE / 'all-outcomes.json')
    require(len(old) == 651 and len(outcomes) == 3 and rows == old + outcomes,
            '654 ledger differs from independent651 plus original new outcomes')
    expected = [c['name'].split(':')[1] for c in source['cases']]
    require(set(c['name'] for c in source['cases']) == set(predecessor.CATALOG) and
            [r['name'] for r in outcomes] == expected and
            [c['source_name'] for c in plan['cases']] == [c['name'] for c in source['cases']],
            '654 case/producer membership differs')
    require(state.get('total') == 3 and state.get('workers') == 8 and
            set(state['cases']) == set(expected) and all(
                state['cases'][n].get('status') == 'PASS' and
                state['cases'][n].get('vdb_valid') is True and
                state['cases'][n].get('reused') is False and
                state['cases'][n].get('passed_only') is True for n in expected),
            '654 checkpoint case evidence differs')
    for row in rows:
        proof.baseline_row(row, plan['image'], plan['simv'])
    for producer in list(proof.plans.values()):
        proof.hashes(producer['files'])
    checked.base.admission.admitted(rows, plan['simv'])
    for item, case, row in zip(source['cases'], plan['cases'], outcomes):
        evidence.precheck(item, proof)
        require(Path(row['vdb']).resolve().is_relative_to(BASELINE / 'results' / case['name']) and
                case['timeout_s'] == item['timeout_s'] <= 300 and
                case['elf_sha256'] == proof.files[str(evidence.full.absolute(item['binary']))],
                'new producer/ELF/budget differs')
        module = importlib.import_module(predecessor.CATALOG[item['name']])
        if not hasattr(module, 'runtime_proof'):
            old_runtime(module, BASELINE, plan, row, proof)
    bits = proof.read(BASELINE / 'combined-bits.json')
    require(bits['tests'] == [r['vdb'] for r in rows], '654 bitmap membership differs')
    proof.hashes(bits['input_hashes'])
    inputs = proof.pin(BASELINE / 'combined-dve/inputs.txt').read_text().splitlines()
    selected = proof.pin(BASELINE / 'combined-dve/selected_tests.txt').read_text().splitlines()
    require(inputs == [plan['design_vdb'], *[r['vdb'] for r in rows]] and selected ==
            [str(Path(r['vdb']).with_suffix('') / r['coverage_test']) for r in rows],
            '654 actual DVE membership differs')
    require(checked.full.base.inventory(Path(plan['design_vdb'])) == plan['design_files'],
            'design VDB drift')
    for stage in ('prepare', 'summarize'):
        report = proof.read(BASELINE / (stage + '-hash-session.json'))
        require(report.get('status') == 'PASS' and report.get('finished') is True and
                report['unique_files'] == report['final_rehashed'] > 0,
                'predecessor final rehash incomplete')
    return rows, bits


def immutable_inputs(spec, output, plan=None, selection=None):
    receipt = evidence.full.read(COMPLETION / 'completion.json')
    baseline = evidence.full.read(BASELINE / 'plan.json')
    rows = evidence.full.read(BASELINE / 'all-passed-outcomes.json')
    paths = set(receipt['files']) | set(baseline['files']) | set(spec.get('files', {}))
    paths.update(str(BASELINE / n) for n in BASELINE_IDENTITY)
    paths.update(str(p / n) for p, names in (
        (COMPLETION, ('completion.json', 'checkpoint.json')),
        (BASELINE, ('checkpoint.json', 'plan.json', 'plan.sha256.json', 'collection.json',
                    'all-outcomes.json', 'all-passed-outcomes.json', 'combined-bits.json')))
        for n in names)
    paths.update(p for row in rows for p in row['files'])
    if plan:
        paths.update(plan['files'])
    if selection is not None:
        paths.add(str(selection))
    for case in spec['cases']:
        paths.update(case['sources']); paths.update(case['evidence']); paths.add(case['binary'])
    paths.update(str(Path(m.__file__)) for m in hashes.verification_modules())
    result = []
    for value in sorted(paths):
        path = evidence.full.absolute(value).absolute()
        if not path.is_relative_to(output.absolute()) and not path.resolve().is_relative_to(output.resolve()):
            require(path.is_file(), 'immutable input is not a file: ' + str(path))
            result.append(path)
    for value in sorted({baseline['design_vdb'], *[r['vdb'] for r in rows]}):
        path = Path(value).resolve(strict=True)
        require(path.is_dir() and not path.is_relative_to(output.resolve()), 'invalid historical VDB root')
        result.append(path)
    return result


def case_limits(cases, modules, bits):
    names = {c['name'] for c in cases}
    require(0 < len(cases) <= 8 and len(names) == len(cases) and names <= set(modules) and
            {str(Path(modules[n].__file__).resolve()) for n in names} ==
            {str(Path(m.__file__).resolve()) for m in modules.values()},
            'selected adapter membership differs')
    for case in cases:
        require(type(case['timeout_s']) is int and 0 < case['timeout_s'] <= 1800, 'case exceeds measured 1800s repair budget')
        require(case.get('targets') and case.get('rationale'), 'missing coverage target/rationale')
        for target in case['targets']:
            require(target.startswith('ara_tb.dut.i_ara_soc.i_system.') and any(
                scope == target or scope.startswith(target + '.')
                for metric in bits['metrics'].values() for scope in metric), 'unmeasured target')


def pin_sources(proof):
    for module in hashes.verification_modules():
        proof.pin(Path(module.__file__))


def composition_producer(row):
    if row.get('kind') == predecessor.gap65.KIND:
        require(row.get('producer') == str(HISTORY), 'foreign gap65 producer identity')
        return HISTORY
    targets = [p for p in Path(row['vdb']).parents
               if p.parent.name == 'results' and p.name == row['name']]
    require(len(targets) == 1, 'foreign historical producer layout')
    return targets[0].parent.parent


def composition_inputs(initial, output):
    """Report/new-precheck files only; no old receipt leaf expansion or VDB trees."""
    paths = set(initial['files']) | {str(BASELINE / n) for n in BASELINE_IDENTITY}
    paths.update(str(COMPLETION / n) for n in ('completion.json', 'checkpoint.json'))
    rows = evidence.full.read(BASELINE / 'all-passed-outcomes.json')
    pending = [BASELINE, HISTORY, predecessor.gap65.BASELINE,
               *[composition_producer(r) for r in rows]]
    seen = set()
    while pending:
        producer = Path(pending.pop())
        if producer in seen:
            continue
        seen.add(producer)
        for name in ('plan.json', 'plan.sha256.json', 'collection.json',
                     'all-outcomes.json', 'all-passed-outcomes.json'):
            path = producer / name
            if path.is_file():
                paths.add(str(path))
        plan = evidence.full.read(producer / 'plan.json')
        collection = evidence.full.read(producer / 'collection.json')
        paths.update(collection['reports'])
        selection = (plan.get('source_selection') or {}).get('selection')
        if selection:
            paths.add(selection)
            if producer == BASELINE:
                paths.update(evidence.full.read(selection)['files'])
        paths.add(str(producer / 'combined-dve/inputs.txt'
                      if (producer / 'combined-dve').is_dir() else producer / 'dve/inputs.txt'))
        prior = (plan.get('source_selection') or {}).get('baseline')
        if prior:
            pending.append(Path(prior))
    paths.update(str(p) for p in (predecessor.SCRIPT, Path(composer.__file__),
                                 Path(hashes.__file__)))
    paths.update(str(Path(m.__file__)) for m in hashes.verification_modules())
    paths.update(str(p / 'outcomes' / (r['name'] + '.json'))
                 for r in rows for p in [composition_producer(r)])
    for case in initial['cases']:
        paths.update(case['sources']); paths.update(case['evidence']); paths.add(case['binary'])
        for value in case['evidence']:
            path = evidence.full.absolute(value)
            if path.name in ('tool_hashes.json', 'link-inputs.json', 'protected-inputs.json',
                             'artifact_hashes.json', 'source_hashes.json'):
                paths.update(evidence.full.read(path))
            elif path.name == 'checked-precheck.json':
                paths.update(evidence.full.read(path)['checked_files'])
    result = []
    for value in sorted(paths):
        path = evidence.full.absolute(value).absolute()
        require(path.is_file() and not path.is_relative_to(output.absolute()) and
                not path.resolve().is_relative_to(output.resolve()), 'invalid composition input: ' + str(path))
        result.append(path)
    return result


def composition_baseline(proof):
    """Seal completed report identity, not image/VDB/oracle admission."""
    state = completion_gate(proof)
    proof.hashes({str(BASELINE / n): h for n, h in BASELINE_IDENTITY.items()})
    predecessor.completed(proof)  # Pinned independent651 receipt, not its 19k leaf hashes.
    plan = proof.plan(BASELINE)
    require(plan.get('checked_extension') == checked.VERSION and plan['workers_max'] == 8 and
            plan['source_selection']['baseline'] == plan['baseline'] == str(HISTORY) and
            plan['baseline_passed'] == 651, 'foreign checked654 sourceplan')
    selection = plan['source_selection']['selection']
    require(selection in plan['files'], 'unbound predecessor selection')
    proof.pin(selection, plan['files'][selection])
    source = proof.read(selection)
    predecessor.check_selection(source, proof)
    for path in (predecessor.SCRIPT, Path(hashes.__file__),
                 *[SCRIPT.parent / (n + '.py') for n in predecessor.CATALOG.values()]):
        require(str(path) in plan['files'], 'unbound predecessor source')
        proof.pin(path, plan['files'][str(path)])
    collection = proof.collection(BASELINE, plan['image'])
    require(collection['status'] == 'PASS' and collection['total'] == collection['passed'] == 654 and
            collection['baseline_passed'] == 651 and collection['new_passed'] == 3 and
            collection['counts'] == {'PASS': 3} and collection['excluded'] == [] and
            collection['cross_image_reuse'] is False, 'incomplete checked654 collection')
    rows = proof.ledger(BASELINE, plan['image'])
    old = proof.ledger(HISTORY, plan['image'])
    original = proof.ledger(predecessor.gap65.BASELINE, plan['image'])
    outcomes = proof.read(BASELINE / 'all-outcomes.json')
    require(len(original) == 650 and len(old) == 651 and old == original + [old[-1]] and
            old[-1]['kind'] == predecessor.gap65.KIND and old[-1]['name'] == predecessor.gap65.ROW and
            rows == old + outcomes and len(outcomes) == 3, '654 independent ledger identity differs')
    names = [c['name'].split(':')[1] for c in source['cases']]
    require(set(c['name'] for c in source['cases']) == set(predecessor.CATALOG) and
            [r['name'] for r in outcomes] == names and
            [c['source_name'] for c in plan['cases']] == [c['name'] for c in source['cases']] and
            state.get('total') == 3 and state.get('workers') == 8 and set(state['cases']) == set(names) and
            all(state['cases'][n].get('status') == 'PASS' and state['cases'][n].get('vdb_valid') is True and
                state['cases'][n].get('passed_only') is True and state['cases'][n].get('reused') is False
                for n in names), '654 producer/checkpoint membership differs')
    for row in rows:
        require(row.get('status') == 'PASS' and row.get('passed_only') is True and
                row.get('vdb_valid') is True and row.get('reused') is False and row.get('returncode') == 0,
                'unverified historical ledger identity')
        producer = composition_producer(row)
        original_plan = proof.plan(producer)
        proof.collection(producer, plan['image'])
        require(original_plan['image'] == plan['image'] and original_plan['simv'] == plan['simv'] and
                proof.read(producer / 'outcomes' / (row['name'] + '.json')) == row,
                'independent producer report differs')
    bits = proof.read(BASELINE / 'combined-bits.json')
    require(bits['tests'] == [r['vdb'] for r in rows] and
            proof.pin(BASELINE / 'combined-dve/inputs.txt').read_text().splitlines() ==
            [plan['design_vdb'], *bits['tests']] and
            proof.pin(BASELINE / 'combined-dve/selected_tests.txt').read_text().splitlines() ==
            [str(Path(r['vdb']).with_suffix('') / r['coverage_test']) for r in rows],
            '654 bitmap/DVE identity differs')
    return rows, bits


def check_selection(spec, proof):
    require(spec.get('schema') == SCHEMA and spec['baseline'] == str(BASELINE) and
            spec['baseline_bits'] == str(BASELINE / 'combined-bits.json') and
            spec['maximum_concurrent_workers'] == 8 and spec['simulations_started'] is False and
            spec.get('full_admission_deferred') is True and spec.get('admission_claimed') is False,
            'foreign successor selection')
    rows, bits = completed(proof)
    proof.hashes(spec['files'])
    modules = load_adapters(spec['adapters'])
    for path in (SCRIPT, Path(composer.__file__), Path(hashes.__file__),
                 BASELINE / 'checkpoint.json', *[Path(m.__file__) for m in unique_modules(modules)]):
        require(str(path) in spec['files'], 'unbound successor source/checkpoint')
    drafts = spec['drafts']
    require(drafts and len(set(drafts)) == len(drafts), 'missing/duplicate drafts')
    original = []
    for path in drafts:
        require(path in spec['files'], 'unbound draft')
        original.extend(proof.read(path)['cases'])
    require(original == spec['cases'], 'sealed draft cases changed')
    case_limits(original, modules, bits)
    # Re-run duplicate name/ELF admission against the exact inherited corpus.
    require(composer.merge_cases([(p, proof.read(p)) for p in drafts], rows,
            lambda p: proof.files[str(proof.pin(p))]) == original, 'case composition differs')
    return rows


def compose(drafts, output, bindings):
    require(not output.exists(), 'new selection file required')
    require(drafts and len(set(drafts)) == len(drafts), 'missing/duplicate drafts')
    completion_gate(evidence.Evidence())
    modules = install(bindings)
    proof = evidence.Evidence()
    initial = dict(files={}, cases=[])
    for path in drafts:
        initial['cases'].extend(proof.read(path)['cases'])
    initial['files'].update(proof.files)
    with hashes.scoped_hashes(output, immutable_roots=composition_inputs(initial, output)):
        rows, bits = composition_baseline(proof)
        cases = composer.merge_cases([(p, proof.read(p)) for p in drafts], rows,
                                     lambda p: proof.files[str(proof.pin(p))])
        case_limits(cases, modules, bits)
        for case in cases:
            evidence.precheck(case, proof)
        pin_sources(proof)
        for path in (SCRIPT, Path(composer.__file__), Path(hashes.__file__),
                     *[Path(m.__file__) for m in unique_modules(modules)]):
            proof.pin(path)
        spec = dict(schema=SCHEMA, baseline=str(BASELINE),
            baseline_bits=str(BASELINE / 'combined-bits.json'), cases=cases,
            adapters=bindings, drafts=[str(p) for p in drafts], files=dict(proof.files),
            maximum_concurrent_workers=8, simulations_started=False,
            full_admission_deferred=True, admission_claimed=False)
    with output.open('x') as stream:
        json.dump(spec, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return spec


def prepared_contract(plan, spec):
    require(plan['source_selection'] == {'baseline': str(BASELINE),
            'selection': plan['source_selection']['selection']} and plan['baseline_passed'] == 654 and
            plan['workers_max'] == 8 and len(plan['cases']) == len(spec['cases']) and
            [c['source_name'] for c in plan['cases']] == [c['name'] for c in spec['cases']] and
            all(type(c['timeout_s']) is int and 0 < c['timeout_s'] <= 1800 and
                c['timeout_s'] == item['timeout_s'] for c, item in zip(plan['cases'], spec['cases'])),
            'successor worker/producer/budget differs')
    require(str(SCRIPT) in plan['files'], 'successor sourceplan is not bound')
    require(plan['baseline'] == str(BASELINE) and
            plan['baseline_bits'] == str(BASELINE / 'combined-bits.json'), 'successor baseline drift')


def install_stage_cache(spec):
    prepare, summarize = checked.prepare, checked.summarize
    original_validate = evidence.validate

    def validate(selection):
        proof = evidence.Evidence()
        require(proof.read(selection) == spec, 'selection changed before admission')
        rows = check_selection(spec, proof)
        cases = [evidence.precheck(c, proof) for c in spec['cases']]
        pin_sources(proof)
        return proof, rows, cases

    evidence.validate = validate

    def cached_prepare(output, selection):
        require(not output.exists(), 'new output directory required')
        try:
            completion_gate(evidence.Evidence())
            with hashes.scoped_hashes(output,
                    immutable_roots=immutable_inputs(spec, output, selection=selection)) as session:
                previous_script = checked.full.SCRIPT
                checked.full.SCRIPT = SCRIPT
                try:
                    prepare(output, selection)
                finally:
                    checked.full.SCRIPT = previous_script
                prepared = evidence.full.read(output / 'plan.json')
                prepared_contract(prepared, spec)
                require(prepared['source_selection']['selection'] == str(selection),
                        'prepared selection path changed')
                wrapper = Path(prepared['wrapper']).read_text()
                require(str(SCRIPT) in wrapper and '--coverage-exec' in wrapper,
                        'coverage wrapper does not call successor')
            report = output / 'prepare-hash-session.json'
            evidence.full.save(report, dict(status='PASS', **session.stats()))
            plan = evidence.full.read(output / 'plan.json')
            require(plan == prepared, 'post-rehash prepared plan changed')
            plan['files'].update(evidence.full.pins([report, Path(hashes.__file__)]))
            evidence.full.save(output / 'plan.json', plan)
            evidence.full.save(output / 'plan.sha256.json', evidence.full.pins([output / 'plan.json']))
            require(evidence.full.read(output / 'plan.json') == plan, 'published plan differs')
            evidence.full.check({str(p): plan['files'][str(p)] for p in (report, Path(hashes.__file__))})
            evidence.full.check(evidence.full.read(output / 'plan.sha256.json'))
        except Exception as error:
            checked.failure(output, 'closure92 prepare/final rehash', error)
            raise

    def cached_summarize(output, plan):
        completion_gate(evidence.Evidence())
        with hashes.scoped_hashes(output, immutable_roots=immutable_inputs(spec, output, plan)) as session:
            prepared_contract(plan, spec)
            result = summarize(output, plan)
        evidence.full.save(output / 'summarize-hash-session.json', dict(status='PASS', **session.stats()))
        return result

    checked.prepare, checked.summarize = cached_prepare, cached_summarize
    return original_validate


def coverage_command(config, args, cwd, plan):
    vector = '+VECTOR_TRACE=' + str(cwd / 'vector_trace.csv')
    vectors = [a for a in args if a.startswith('+VECTOR_TRACE')]
    require(vectors in ([], [vector]), 'vector trace override forbidden')
    command = checked.full.batch.adapter_command(config, args, cwd)
    require(len([a for a in args if a.startswith('+TESTCASE=')]) == 1,
            'one successor testcase required')
    names = {c['source_name'].split(':')[1] for c in plan['cases']}
    name = next(a.split('=', 1)[1] for a in args if a.startswith('+TESTCASE='))
    require(name in names, 'foreign successor trace case')
    required = TRACE_PLUSARGS.get(name, ())
    profiles = [a for a in args if a.startswith(('+QBS_PERF', '+AKV_PERF'))]
    require(profiles in ([], list(required)), 'runtime trace profile override forbidden')
    extras = [flag for flag in required if flag not in profiles]
    return [*command, *extras, *([] if vectors else [vector])]


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--coverage-exec':
        config = evidence.full.read(sys.argv[2])
        cwd = Path.cwd().resolve()
        output = Path(config['results']).parent
        plan = checked.frozen(output)
        require(str(SCRIPT) in plan['files'], 'coverage successor source unbound')
        command = coverage_command(config, sys.argv[3:], cwd, plan)
        with (cwd / 'coverage.command.json').open('x') as stream:
            json.dump(dict(command=command, cwd=str(cwd)), stream)
        os.execv(command[0], command)
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for flag in ('compose', 'prepare', 'launch', 'execute', 'start'):
        modes.add_argument('--' + flag, action='store_true')
    modes.add_argument('--worker'); modes.add_argument('--directed')
    parser.add_argument('--draft', type=Path, action='append', default=[])
    parser.add_argument('--adapter', action='append', default=[], metavar='GAP=MODULE')
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.compose:
        bindings = {}
        for value in args.adapter:
            gap, sep, module = value.partition('=')
            require(sep and gap not in bindings, 'invalid/duplicate --adapter')
            bindings[gap] = module
        require(args.selection is not None, '--selection required')
        compose([p.resolve(strict=True) for p in args.draft], args.selection.resolve(), bindings)
        return 0
    require(not args.adapter and not args.draft and args.output is not None,
            '--adapter/--draft are compose-only; --output required')
    output = checked.full.base.checked_output(args.output)
    if args.prepare or args.start:
        require(args.selection is not None, '--selection required')
        completion_gate(evidence.Evidence())
        spec = evidence.full.read(args.selection.resolve(strict=True))
    else:
        plan = checked.frozen(output)
        selection = plan['source_selection']['selection']
        require(selection in plan['files'], 'runtime selection not frozen')
        evidence.full.check({selection: plan['files'][selection]})
        spec = evidence.full.read(selection)
    require(spec.get('schema') == SCHEMA, 'foreign successor schema')
    checked.SCRIPT = SCRIPT
    install(spec['adapters'])
    install_stage_cache(spec)
    if args.start:
        require(os.environ.get('ARA_CHECKPOINT_UNIT') == 'ara-coverage-' + output.name + '.service'
                and os.environ.get('INVOCATION_ID'), 'registered service required')
        checked.prepare(output, args.selection.resolve(strict=True))
        sys.argv = [str(SCRIPT), '--output', str(output), '--execute']
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
