#!/usr/bin/env python3
"""Evidence-bounded retries and lossless test shards on the frozen VCS image.

Prior timeouts remain immutable. Retry aliases retain exactly the original
ELF, and each budget requires a recorded rationale. Any new non-PASS stops
dispatch rather than silently growing timeouts or modifying RTL.
"""
from dataclasses import replace
from pathlib import Path
import sys

import extend_gap_coverage as gap

extension, batch = gap.extension, gap.batch
SCRIPT = Path(__file__).resolve()
selection_data = {}
previous_root = None
normal_select = gap.select_tests
normal_prepare = gap.original_prepare
normal_worker = batch.worker


def select_tests(catalog, previous, names):
    retries = selection_data.get('retries', {})
    fresh = [n for n in names if n not in retries]
    selected = normal_select(catalog, previous, fresh) if fresh else []
    if len(names) != len(set(names)):
        raise ValueError('duplicate repair alias')
    for alias, source in retries.items():
        if alias not in names or any(c.get('test') == alias for c in previous['cases']):
            raise ValueError(f'invalid retry alias: {alias}')
        cases = [c for c in previous['cases'] if c.get('test') == source]
        if len(cases) != 1 or cases[0]['kind'] != 'directed':
            raise ValueError(f'expected one archived directed case: {source}')
        case = cases[0]
        outcome = batch.read(previous_root / 'outcomes' / (case['name'] + '.json'))
        if outcome['status'] != 'TIMEOUT':
            raise ValueError(f'not an archived timeout: {source}')
        elf = Path(case['frozen_elf'])
        batch.check({str(elf): case['elf_sha256']})
        test = batch.TestCase(**dict(case['directed_test'], binary=elf))
        test = replace(test, name=alias, testcase='repair_' + test.testcase)
        selected.append((alias, test, case['elf_sha256']))
    order = {name: i for i, name in enumerate(names)}
    return sorted(selected, key=lambda row: order[row[0]])


def prepare(output, previous, selection):
    global selection_data, previous_root
    selection_data, previous_root = batch.read(selection), previous
    normal_prepare(output, previous, selection)
    plan = batch.read(output / 'plan.json')
    for case in plan['cases']:
        if case['name'] in plan['reused']:
            continue
        setting = selection_data['budgets'][case['test']]
        budget = setting['seconds']
        if type(budget) is not int or not 60 <= budget <= 1800 or not setting['reason']:
            raise ValueError('each repair needs a bounded, justified budget')
        case.update(timeout_s=budget, timeout_rationale=setting['reason'])
        original = selection_data.get('retries', {}).get(case['test'])
        if original:
            case['repair_of'] = original
        elif case['test'].startswith('app:'):
            app = batch.ROOT / 'apps' / case['test'].split(':', 1)[1]
            case['source_files'].update(batch.pins([
                p for p in app.rglob('*') if p.is_file() and
                p.suffix in ('.c', '.h', '.cpp', '.S')]))
    plan['files'].update(batch.pins([Path(gap.__file__), *[
        batch.ROOT / path for path in selection_data.get('source_dependencies', [])]]))
    batch.save(output / 'plan.json', plan)
    batch.save(output / 'plan.sha256.json', batch.pins([output / 'plan.json']))
    batch.frozen(output, all_cases=True)


def worker(output, name):
    rc = normal_worker(output, name)
    record = batch.read(output / 'outcomes' / (name + '.json'))
    if record.get('status') != 'PASS':
        batch.save(output / ('repair_stop_' + name + '.json'), {
            'case': name, 'status': record.get('status'),
            'policy': 'stop dispatch; inspect evidence before further changes'})
        return 1
    return rc


extension.SCRIPT = gap.SCRIPT = batch.SCRIPT = SCRIPT
extension.select_tests = select_tests
extension.prepare = prepare
batch.worker = worker

if __name__ == '__main__':
    result = extension.main()
    if result and '--execute' in sys.argv:
        output = Path(sys.argv[sys.argv.index('--output') + 1])
        stops = sorted(output.glob('repair_stop_*.json'))
        if stops:
            state = batch.read(output / 'checkpoint.json')
            state['reason'] = 'Repair non-PASS: ' + ', '.join(
                batch.read(p)['case'] for p in stops)
            batch.save(output / 'checkpoint.json', state)
    raise SystemExit(result)
