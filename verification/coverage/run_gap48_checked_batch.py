#!/usr/bin/env python3
"""Run the next reviewed gap cases together without replacing frozen checkers."""
import argparse
import importlib
from pathlib import Path

import coverage_evidence as evidence
import run_checked_extension as checked

SCRIPT = Path(__file__).resolve()
COMPOSER = SCRIPT.parents[1] / 'tests/compose_gap48_selection.py'
require = evidence.require
CATALOG = (
    ('rvv:csr_gap44_absent', False, 'run_gap44_csr_checked_extension'),
    ('app:qbs_gap45_context', False, 'run_gap45_qbs_checked_extension'),
    ('app:akv_gap46_skew_context', False, 'run_gap46_akv_checked_extension'),
    ('rvv:vgap47_sv39_indexed_pmp0', False, 'run_gap47_rvv_checked_extension_v2'),
    ('app:qbs_gap49_payload_skew', False, 'run_gap49_payload_checked_extension'),
)


def adapter_names(cases):
    result = []
    for case in cases:
        name = case['name']
        matches = [module for key, prefix, module in CATALOG
                   if (name.startswith(key) if prefix else name == key)]
        require(len(matches) == 1, 'case has no unique reviewed adapter: ' + name)
        if matches[0] not in result:
            result.append(matches[0])
    require(result, 'empty batch')
    return result


def check_composition(spec, proof):
    require(spec.get('status') == 'COMPOSED_REQUIRES_CHECKED_ADMISSION',
            'not a composed reviewed selection')
    meta = spec['composition']
    require(meta['maximum_concurrent_workers'] == 8 and meta['case_limit_seconds'] == 600,
            'composition budgets differ')
    require(str(SCRIPT) not in meta['files'], 'runner cannot approve itself through draft data')
    require(str(COMPOSER) in meta['files'], 'composer is not bound')
    proof.hashes(meta['files'])
    drafts = meta['drafts']
    require(drafts and len(drafts) == len(set(drafts)), 'empty or duplicate drafts')
    original = []
    for path in drafts:
        require(path in meta['files'], 'draft is not bound')
        original.extend(proof.read(path)['cases'])
    require(spec['cases'] == original, 'composed cases differ from sealed drafts')
    require(len({c['name'].split(':')[-1] for c in original}) == len(original),
            'duplicate worker labels')
    require(all(type(c['timeout_s']) is int and 0 < c['timeout_s'] <= 600 for c in original),
            'invalid case budget')
    baseline = Path(spec['baseline']).resolve(strict=True)
    expected = baseline / 'combined-bits.json'
    require(spec['baseline_bits'] == str(expected) and str(expected) in meta['files'],
            'baseline bitmap is not bound')
    required = {str(baseline / name) for name in
                ('checkpoint.json', 'collection.json', 'all-passed-outcomes.json',
                 'combined-bits.json')}
    required.update(case['binary'] for case in original)
    require(required <= meta['files'].keys(), 'composition lacks required input hashes')
    checkpoint, collection = (proof.read(baseline / name) for name in
                              ('checkpoint.json', 'collection.json'))
    require(collection['status'] in ('PASS', 'COMPLETE_WITH_FAILURES') and
            checkpoint['coverage_status'] == 'COMPLETE' and
            collection['passed'] == checkpoint['aggregate_passed'] == meta['baseline_passed'],
            'baseline completion/count differs')
    return adapter_names(original)


def runtime_selection(plan):
    selection = Path(plan['source_selection']['selection'])
    require(str(selection) in plan['files'], 'selection is not frozen')
    checked.full.check({str(selection): plan['files'][str(selection)]})
    spec = checked.full.read(selection)
    expected = [(case['source_name'], case['timeout_s'], case['elf_sha256'])
                for case in plan['cases']]
    actual = [(case['name'], case['timeout_s'], plan['files'].get(case['binary']))
              for case in spec['cases']]
    require(actual == expected, 'selection case identities differ from frozen plan')
    return spec


def install(modules):
    for module in modules:
        module.install_hooks()
    original_validate = evidence.validate

    def validate(selection):
        proof = evidence.Evidence()
        spec = proof.read(selection)
        names = check_composition(spec, proof)
        require(names == [module.__name__ for module in modules], 'loaded adapters differ')
        for path in (SCRIPT, COMPOSER, Path(checked.__file__), Path(evidence.__file__),
                     *[Path(module.__file__) for module in modules]):
            proof.pin(path)
        full, rows, cases = original_validate(selection)
        require(len(rows) == spec['composition']['baseline_passed'], 'admitted count differs')
        for path, digest in proof.files.items():
            require(path not in full.files or full.files[path] == digest,
                    'composition changed during full admission')
        full.hashes(proof.files)
        return full, rows, cases

    evidence.validate = validate


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--prepare', action='store_true')
    args, _ = parser.parse_known_args()
    if args.prepare:
        require(args.selection is not None, 'prepare needs a selection')
        selection = args.selection.resolve(strict=True)
        spec = checked.full.read(selection)
    else:
        plan = checked.frozen(args.output.resolve(strict=True))
        spec = runtime_selection(plan)
    modules = [importlib.import_module(name) for name in adapter_names(spec['cases'])]
    checked.SCRIPT = SCRIPT
    install(modules)
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
