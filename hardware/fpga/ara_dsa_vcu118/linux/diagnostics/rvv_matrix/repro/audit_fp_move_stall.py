"""Audit FP slide-up stalls without inferring unobserved internal queue state."""
import argparse
import json
from pathlib import Path
import re
from audit_permute_stall import inspect
from audit_slide import require
from trace_masks import sha


def trigger(output):
    lines = output.strip().splitlines()
    require(lines and lines[-1].startswith('RVV_MOVE_BEGIN '), 'No final unreturned call')
    tokens = lines[-1].split()[1:]
    require(all(re.fullmatch(r'\w+=\d+', t) for t in tokens), 'Malformed trigger')
    fields = {k: int(v) for k, v in (t.split('=') for t in tokens)}
    require(len(fields) == len(tokens) and set(fields) == {
        'seed', 'scalar', 'invalid_box', 'op', 'vl', 'mask', 'sticky', 'vstart', 'cap', 'completed'},
        'Missing or duplicate trigger fields')
    fields.pop('completed')
    return fields


def audit(original_report, trace_root, trace_report, single_root, single_report, cross):
    sm = json.loads((single_root / 'manifest.json').read_text())
    sc, = sm['cases']
    require(sc['scenario_role'] == 'single_original_trial' and sc['configurations'] == 1,
            'Not a single original trial')
    original_name = sc['original_name']
    original_elf = single_root / sc['name'] / 'original_rebuilt.elf'
    rows = [inspect(original_report, original_elf, original_name, cross, False, '38805c57')]
    expected = {k: v for k, v in sc['selected_trial'].items() if k != 'completed'}
    require(expected['op'] == 2, 'Not the measured slide-up operation')
    require(sm['trace_report_sha256'] == sha(trace_report) and
            sm['trace_manifest_sha256'] == sha(trace_root / 'manifest.json'), 'Trace lineage changed')
    for root, path, role in ((trace_root, trace_report, 'original_sequence_trace'),
                             (single_root, single_report, 'single_original_trial')):
        m = json.loads((root / 'manifest.json').read_text()); c, = m['cases']
        require(m['original_report_sha256'] == sha(original_report), 'Original report changed')
        require(c['scenario_role'] == role and c['original_name'] == original_name,
                'Wrong scenario lineage')
        require(c['original_elf_sha256'] == sha(original_elf) ==
                sha(root / c['name'] / 'original_rebuilt.elf'), 'Original ELF changed')
        for file, digest in c['scenario_sources'].items():
            require(sha(root / c['name'] / file) == digest, 'Scenario source changed')
        binary = root / 'overlay/opt/ara-tests' / c['name']
        require(sha(binary) == c['sha256'], 'Candidate ELF changed')
        row = inspect(path, binary, c['name'], cross, False, '38805c57')
        report = json.loads(path.read_text()); report = report.get('report', report)
        r, = [r for r in report['results'] if r['name'] == c['name']]
        row['trigger'] = trigger(r['output'])
        require(row['trigger'] == expected, 'Different measured stalled trial')
        rows.append(row)
    return dict(confirmed=True, cases=rows, original_uninstrumented_trigger_recorded=False,
                internal_rtl_root_cause_proven=False,
                scope='Same original opcode stall; same measured trace and single-trial inputs',
                caveat='Snapshot PCs do not establish head-valid or blocked internal unit')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('original-report', 'trace-root', 'trace-report', 'single-root', 'single-report', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--cross', required=True)
    a = p.parse_args()
    result = audit(a.original_report, a.trace_root, a.trace_report, a.single_root, a.single_report, a.cross)
    a.out.mkdir(exist_ok=False)
    for role, path in (('original', a.original_report), ('trace', a.trace_report), ('single', a.single_report)):
        (a.out / (role + '_report.json')).write_bytes(path.read_bytes())
    (a.out / 'symptoms.json').write_text(json.dumps(result, indent=2) + '\n')
    print('CONFIRMED', result['confirmed'])


if __name__ == '__main__':
    main()
