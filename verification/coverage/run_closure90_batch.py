#!/usr/bin/env python3
"""One checked three-case closure batch on the independently completed 651 tip."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import coverage_evidence as evidence
import run_checked_extension as checked
import finalize_gap65_observed as gap65
import closure_scorecard
import coverage_hash_session

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(ROOT / 'verification/tests'))
import compose_gap48_selection as composer

BASELINE = gap65.RUNTIME
COMPLETION = ROOT / 'verification/out/gap65-report-only-recovery-20261005-01/reports'
COMPLETION_SHA = '5057d845a6d75d070fcef33f92a106719b9b361fdfa6bdeecfda39af35f95209'
CHECKPOINT_SHA = '1a4e556c0e87775338cf0eaded88c79135e61916ceee4136ff7175fa16fb9771'
CATALOG = {
    'rvv:sv39_gap68_warm_permissions_pmp0': 'run_gap68_system_checked_extension',
    'rvv:vgap69_vf_odd_vd': 'run_gap69_vf_checked_extension',
    'rvv:vgap70_indexed_fault_recover': 'run_gap70_indexed_checked_extension',
}
require = evidence.require


def completed(proof):
    report = closure_scorecard.scorecard(BASELINE, COMPLETION)
    require(report['passed'] == 651, 'require checked651 predecessor')
    proof.pin(COMPLETION / 'checkpoint.json', CHECKPOINT_SHA)
    proof.pin(COMPLETION / 'completion.json', COMPLETION_SHA)
    proof.hashes(report['report_pins'])
    receipt = proof.read(COMPLETION / 'completion.json')
    require(receipt['hash_stats']['unique_files'] == receipt['hash_stats']['final_rehashed'] ==
            len(receipt['files']),
            'incomplete independent final rehash')
    # Bind the completed report/producer to the independent recovery receipt;
    # full checked admission below still validates every historical PASS row.
    for path in (BASELINE / 'collection.json', BASELINE / 'plan.json',
                 BASELINE / 'all-passed-outcomes.json', BASELINE / 'combined-bits.json'):
        require(str(path) in receipt['files'], 'recovery receipt does not bind producer report')
        proof.pin(path, receipt['files'][str(path)])
    return report


def compose(drafts, output):
    require(not output.exists(), 'new selection file required')
    require(drafts and len(set(drafts)) == len(drafts), 'missing/duplicate drafts')
    proof = evidence.Evidence()
    completed(proof)
    rows = proof.read(BASELINE / 'all-passed-outcomes.json')
    bits = proof.read(BASELINE / 'combined-bits.json')

    def pin(path):
        resolved = proof.pin(path)
        return proof.files[str(resolved)]

    cases = composer.merge_cases([(p, proof.read(p)) for p in drafts], rows, pin)
    require(set(c['name'] for c in cases) <= set(CATALOG) and len(cases) <= 3,
            'case outside reviewed three-case batch')
    for item in cases:
        require(item['timeout_s'] <= 300, 'bounded directed test exceeds 300 seconds')
        for target in item['targets']:
            require(target.startswith('ara_tb.dut.i_ara_soc.i_system.') and any(
                scope == target or scope.startswith(target + '.')
                for metric in bits['metrics'].values() for scope in metric),
                'target outside frozen measured hierarchy')
    for path in (SCRIPT, Path(composer.__file__), Path(closure_scorecard.__file__)):
        proof.pin(path)
    spec = dict(schema='closure90-batch-v1', baseline=str(BASELINE),
        baseline_bits=str(BASELINE / 'combined-bits.json'), cases=cases,
        completion=str(COMPLETION), drafts=[str(p) for p in drafts], files=proof.files,
        maximum_concurrent_workers=8, simulations_started=False)
    with output.open('x') as stream:
        json.dump(spec, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('COMPOSED ONLY: %d new cases on checked651' % len(cases), flush=True)
    return spec


def check_selection(spec, proof):
    require(spec.get('schema') == 'closure90-batch-v1' and
            spec['baseline'] == str(BASELINE) and spec['completion'] == str(COMPLETION) and
            spec['baseline_bits'] == str(BASELINE / 'combined-bits.json') and
            spec['maximum_concurrent_workers'] == 8 and spec['simulations_started'] is False,
            'foreign closure batch/predecessor')
    completed(proof)
    proof.hashes(spec['files'])
    require(str(SCRIPT) in spec['files'] and str(Path(composer.__file__)) in spec['files'],
            'unbound batch/composer source')
    drafts = spec['drafts']
    require(drafts and len(drafts) == len(set(drafts)), 'missing/duplicate bound drafts')
    original = []
    for path in drafts:
        require(path in spec['files'], 'unbound draft')
        original.extend(proof.read(path)['cases'])
    require(spec['cases'] == original and 0 < len(original) <= 3,
            'selected case differs from sealed draft')
    require(len({c['name'] for c in original}) == len(original) and
            all(c['name'] in CATALOG and type(c['timeout_s']) is int and
                0 < c['timeout_s'] <= 300 for c in original), 'case identity/budget differs')


def install(spec):
    names = list(dict.fromkeys(CATALOG[c['name']] for c in spec['cases']))
    # Install the historical special row first; new adapters may wrap this
    # method to add their stricter runtime result audits.
    gap65.install_hooks()
    for name in names:
        module = importlib.import_module(name)
        require(Path(module.__file__).resolve() == SCRIPT.parent / (name + '.py'),
                'foreign case adapter')
        module.install_hooks()
    original_validate = evidence.validate

    def validate(selection):
        bound = evidence.Evidence()
        current = bound.read(selection)
        require(current == spec, 'selection changed before full admission')
        check_selection(current, bound)
        result, rows, cases = original_validate(selection)
        require(len(rows) == 651, 'checked predecessor count differs')
        for path in (SCRIPT, Path(gap65.__file__), Path(closure_scorecard.__file__),
                     *[SCRIPT.parent / (n + '.py') for n in names]):
            bound.pin(path)
        result.hashes(bound.files)
        return result, rows, cases

    evidence.validate = validate


def immutable_inputs(spec, output, plan=None):
    receipt = evidence.full.read(COMPLETION / 'completion.json')
    paths = set(receipt['files']) | set(spec['files'])
    paths.update((str(COMPLETION / 'completion.json'), str(COMPLETION / 'checkpoint.json')))
    if plan:
        paths.update(plan['files'])
    for item in spec['cases']:
        paths.update(item['sources'])
        paths.update(item['evidence'])
        paths.add(item['binary'])
    paths.update(str(Path(m.__file__)) for m in coverage_hash_session.verification_modules())
    result = []
    for value in sorted(paths):
        path = evidence.full.absolute(value).absolute()
        if not path.is_relative_to(output) and not path.resolve().is_relative_to(output.resolve()):
            require(path.is_file(), 'immutable input is not a file: %s' % path)
            result.append(path)
    # File pins detect byte changes; directory snapshots additionally detect
    # VDB membership changes during the final uncached rehash window.
    rows = evidence.full.read(BASELINE / 'all-passed-outcomes.json')
    design = evidence.full.read(BASELINE / 'plan.json')['design_vdb']
    for value in sorted({design, *[r['vdb'] for r in rows]}):
        path = Path(value).resolve(strict=True)
        require(path.is_dir() and not path.is_relative_to(output.resolve()),
                'invalid immutable historical VDB root')
        result.append(path)
    return result


def install_stage_cache(spec):
    prepare, summarize = checked.prepare, checked.summarize

    def cached_prepare(output, selection):
        require(not output.exists(), 'new output directory required')
        try:
            with coverage_hash_session.scoped_hashes(output,
                    immutable_roots=immutable_inputs(spec, output)) as session:
                previous_script = checked.full.SCRIPT
                checked.full.SCRIPT = SCRIPT
                try:
                    prepare(output, selection)
                finally:
                    checked.full.SCRIPT = previous_script
                prepared = evidence.full.read(output / 'plan.json')
            # Publication follows the uncached final rehash; output files were
            # never cached while the frozen plan was being generated.
            report = output / 'prepare-hash-session.json'
            evidence.full.save(report, dict(status='PASS', scope='immutable read deduplication only',
                                           **session.stats()))
            plan = evidence.full.read(output / 'plan.json')
            plan['files'].update(evidence.full.pins([report, Path(coverage_hash_session.__file__)]))
            evidence.full.save(output / 'plan.json', plan)
            evidence.full.save(output / 'plan.sha256.json', evidence.full.pins([output / 'plan.json']))
            require({k: v for k, v in plan.items() if k != 'files'} ==
                    {k: v for k, v in prepared.items() if k != 'files'},
                    'post-rehash plan semantics changed')
            require(all(plan['files'][p] == h for p, h in prepared['files'].items()),
                    'post-rehash prepared input pin changed')
            require(evidence.full.read(output / 'plan.json') == plan,
                    'published plan differs')
            evidence.full.check({str(path): plan['files'][str(path)]
                                 for path in (report, Path(coverage_hash_session.__file__))})
            evidence.full.check(evidence.full.read(output / 'plan.sha256.json'))
        except Exception as error:
            checked.failure(output, 'closure prepare/final rehash', error)
            raise

    def cached_summarize(output, plan):
        with coverage_hash_session.scoped_hashes(output,
                immutable_roots=immutable_inputs(spec, output, plan)) as session:
            result = summarize(output, plan)
        evidence.full.save(output / 'summarize-hash-session.json', dict(
            status='PASS', scope='immutable read deduplication only', **session.stats()))
        return result

    checked.prepare, checked.summarize = cached_prepare, cached_summarize


def coverage_command(config, args, cwd):
    require(not any(a.startswith('+VECTOR_TRACE') for a in args),
            'vector trace override not allowed')
    command = checked.full.batch.adapter_command(config, args, cwd)
    names = [a.split('=', 1)[1] for a in args if a.startswith('+TESTCASE=')]
    require(len(names) == 1 and names[0] in {n.split(':')[1] for n in CATALOG},
            'foreign closure trace case')
    return [*command, '+VECTOR_TRACE=' + str(cwd / 'vector_trace.csv')]


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--coverage-exec':
        config = evidence.full.read(sys.argv[2])
        cwd = Path.cwd().resolve()
        command = coverage_command(config, sys.argv[3:], cwd)
        with (cwd / 'coverage.command.json').open('x') as stream:
            json.dump(dict(command=command, cwd=str(cwd)), stream)
        os.execv(command[0], command)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--compose', action='store_true')
    parser.add_argument('--draft', type=Path, action='append')
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--start', action='store_true',
                        help='Within the registered service: checked prepare, then execute')
    args, _ = parser.parse_known_args()
    if args.compose:
        require(args.selection is not None, '--selection output required')
        compose([p.resolve(strict=True) for p in args.draft or []], args.selection.resolve())
        return 0
    require(args.output is not None, '--output required')
    if args.prepare or args.start:
        require(args.selection is not None, '--prepare needs a composed selection')
        spec = evidence.full.read(args.selection.resolve(strict=True))
    else:
        plan = checked.frozen(args.output.resolve(strict=True))
        selection = plan['source_selection']['selection']
        require(selection in plan['files'], 'runtime selection not frozen')
        evidence.full.check({selection: plan['files'][selection]})
        spec = evidence.full.read(selection)
    require(spec.get('schema') == 'closure90-batch-v1', 'foreign batch schema')
    require(all(c['name'] in CATALOG for c in spec['cases']), 'foreign batch case')
    checked.SCRIPT = SCRIPT
    install(spec)
    install_stage_cache(spec)
    if args.start:
        require(not args.prepare and args.selection is not None, '--start requires selection only')
        output = checked.full.base.checked_output(args.output)
        require(os.environ.get('ARA_CHECKPOINT_UNIT') == 'ara-coverage-' + output.name + '.service'
                and os.environ.get('INVOCATION_ID'), 'registered start service required')
        checked.prepare(output, args.selection.resolve(strict=True))
        sys.argv = [str(SCRIPT), '--output', str(output), '--execute']
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
