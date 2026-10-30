#!/usr/bin/env python3
"""Read one completed pair without treating partial trials as performance."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def numeric_summary(receipt, mechanism):
    for key in ('performance_measured', 'independent_protocol_checked', 'post_pins_match'):
        if receipt.get(key) is not True:
            raise ValueError('Missing acceptance: ' + key)
    if receipt.get('state') != 'PASS':
        raise ValueError('Not an accepted result')
    m = receipt['measured']
    if m.get('paired_bitexact') is not True:
        raise ValueError('Missing exact paired output check')
    rows = m['trials']
    field, candidate_key, outputs, commands = (
        ('shared', 'shared_cycles', 1024, 4) if mechanism == 'prefill' else
        ('candidate', 'candidate_cycles', 256, 1))
    if mechanism not in ('prefill', 'register-pv') or len(rows) != 4:
        raise ValueError('Unknown comparison or incomplete pair')
    if [row[field] for row in rows] != [0, 1, 1, 0]:
        raise ValueError('Not ABBA')
    if any(type(row['cycles']) is not int or row['cycles'] <= 0 for row in rows):
        raise ValueError('Invalid cycle count')
    baseline = (rows[0]['cycles']+rows[3]['cycles'])/2
    candidate = (rows[1]['cycles']+rows[2]['cycles'])/2
    if (m['baseline_cycles'] != baseline or m[candidate_key] != candidate or
            not math.isclose(m['speedup'], baseline/candidate, rel_tol=1e-12) or
            m['outputs_per_trial'] != outputs or m['commands_per_trial'] != commands):
        raise ValueError('Measured values disagree with trials/scope')
    return dict(state='ACCEPTED', mechanism=mechanism, baseline_cycles=baseline,
        candidate_cycles=candidate, speedup=baseline/candidate,
        cycle_reduction_percent=100*(baseline-candidate)/baseline,
        baseline_repeats=[rows[0]['cycles'], rows[3]['cycles']],
        candidate_repeats=[rows[1]['cycles'], rows[2]['cycles']],
        outputs_per_trial=outputs, commands_per_trial=commands, whole_model=False,
        scope=m['scope'])


def captured_query(build, measured):
    """Bind a context experiment to its captured query, never infer from cycles."""
    if build.get('context_pair') is not True:
        if 'query_index' in measured or 'visible_tokens' in measured:
            raise ValueError('Context receipt without context build')
        return None
    query = build.get('query_index')
    if (build.get('register_pv') is not True or type(query) is not int or
            not 0 <= query < 20 or
            type(measured.get('query_index')) is not int or
            type(measured.get('visible_tokens')) is not int or
            measured['query_index'] != query or measured['visible_tokens'] != query+1):
        raise ValueError('Captured query identity mismatch')
    return query


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--mechanism', choices=('prefill', 'register-pv'), required=True)
    args = parser.parse_args()
    run = args.run.resolve(strict=True)
    path = run/'result.json'
    if not path.is_file():
        print(json.dumps(dict(state='NO_FINAL_RESULT', run=str(run),
            note='No performance accepted; this does not establish process liveness.')))
        return
    receipt = json.loads(path.read_text())
    summary = numeric_summary(receipt, args.mechanism)
    pins = json.loads((run/'source-pins.json').read_text())
    for source, expected in pins.items():
        if digest(source) != expected:
            raise ValueError('Cannot replay against changed input: '+source)
    state = json.loads((run/'status.json').read_text())
    build = json.loads((Path(state['build'])/'build.json').read_text())
    if (receipt['elf_sha256'] != build['elf_sha256'] or
            digest(build['elf']) != receipt['elf_sha256'] or
            build.get('value_binding') != 'shared_rvv_q8_0' or
            build.get('whole_call') is not True):
        raise ValueError('ELF or production-binding mismatch')
    if args.mechanism == 'prefill':
        sys.path.insert(0, str(HERE/'prefill'))
        from check_strided_native import check_strided_log as check
        from run_production_native import require_production_build
        require_production_build(build)
    else:
        if build.get('register_pv') is not True:
            raise ValueError('Not a register-PV experiment')
        query = captured_query(build, receipt['measured'])
        if query is None:
            from register_pv.check_native import check_log as check
        else:
            from register_pv.context_pair.check_native import check_log as context_check
            def check(text, golden, q4):
                return context_check(text, golden, q4, query)
            summary.update(query_index=query, visible_tokens=query+1)
    golden = ROOT/'verification/out/quant-prefill-capture-20261028-01'/build['kind']/'prefill/block/kqv_out-0.bin'
    log = run/'work/run.vcs.log'
    checked = check(log.read_text(), golden.read_bytes(), int(build['kind']=='q4_0'))
    if checked != receipt['measured']:
        raise ValueError('Replayed checker disagrees with worker receipt')
    summary.update(run=str(run), key_format=build['kind'], value_format='q8_0',
        elf_sha256=receipt['elf_sha256'], receipt_sha256=digest(path),
        log_sha256=digest(log), checker_replayed=True)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
