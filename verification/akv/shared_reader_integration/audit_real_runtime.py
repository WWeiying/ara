#!/usr/bin/env python3
"""Independently recheck completed real-input reader/storage regressions."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from run_real_runtime import s, original, checked_soc, compare_outputs


def compare_commands(old, new):
    s.require(len(old) == len(new) and bool(old), 'Missing or extra command records')
    differences = []
    for index, (before, after) in enumerate(zip(old, new)):
        s.require(set(before) == set(after), 'Command counter schema changed')
        delta = {key:dict(baseline=before[key], candidate=after[key])
                 for key in before if before[key] != after[key]}
        if delta:
            differences.append(dict(ordinal=index, fields=delta))
    return dict(commands=len(old), identical=not differences,
                changed_commands=len(differences), first_differences=differences[:50],
                differences_truncated=len(differences) > 50)


def compare_performance(old, new):
    matched = compare_outputs(old, new)
    cycle_presence = {'cycles' in row for record in (old, new) for row in record['trials']}
    s.require(len(cycle_presence) == 1, 'Asymmetric or partially missing cycle measurements')
    rows = []
    for before, after in zip(old['trials'], new['trials']):
        present = 'cycles' in before and 'cycles' in after
        if present:
            s.require(type(before['cycles']) is int and before['cycles'] > 0 and
                      type(after['cycles']) is int and after['cycles'] > 0,
                      'Invalid complete-call cycles')
        rows.append(dict(case=before.get('case'), trial=before['trial'],
                         mode=before.get('paired', before.get('requested')),
                         baseline_cycles=before.get('cycles'),
                         candidate_cycles=after.get('cycles'),
                         cycle_delta=after['cycles']-before['cycles'] if present else None))
    available = all(row['cycle_delta'] is not None for row in rows)
    no_regression = all(row['cycle_delta'] <= 0 for row in rows) if available else None
    counters_equal = matched['per_call_counters_identical'] is True
    return dict(matched=matched, calls=rows, complete_call_cycles_available=available,
                complete_call_no_regression=no_regression,
                per_call_counter_equivalence=counters_equal,
                resource_regression_gate_pass=counters_equal and no_regression is not False,
                complete_operator_performance_accepted=(available and no_regression is True and
                                                        counters_equal),
                whole_model_performance=False)


def compare_runtime(old, new, commands_old, commands_new):
    comparison = compare_performance(old, new)
    comparison['command_comparison'] = compare_commands(commands_old, commands_new)
    comparison['resource_regression_gate_pass'] &= comparison['command_comparison']['identical']
    comparison['complete_operator_performance_accepted'] &= comparison['resource_regression_gate_pass']
    return comparison


def terminal(run, kind):
    run = run.resolve(strict=True)
    status, report = (s.read_json(run/name) for name in ('status.json', 'result.json'))
    s.require(status.get('state') == report.get('state') == 'PASS' and
              status.get('child_pid') is None and status.get('running_exit_code') == 0 and
              status.get('kind') == report.get('kind') == kind and
              report.get('post_pins_match') is True, 'Need checked terminal runtime PASS')
    receipt = run/'source-pins.json'
    s.require(s.digest(receipt) == report.get('source_pins_sha256'), 'Runtime receipt changed')
    pins = s.read_json(receipt)
    s.verify_pins(pins)
    s.verify_pins(report['evidence_sha256'])
    elf, simv = Path(status['elf']), Path(status['simv'])
    s.require(pins.get(str(elf)) == report.get('elf_sha256') == s.digest(elf), 'ELF drift')
    image = s.hashes(s.image_files(simv))
    s.require(all(pins.get(name) == sha for name, sha in image.items()), 'Unpinned image')
    log, trace, protocol = (run/'work'/name for name in
                           ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
    s.require(all(str(path) in report['evidence_sha256'] for path in (log, trace, protocol)),
              'Missing raw/protocol evidence')
    raw = original.checker(kind)(log.read_text())
    s.require(raw.get('state') == 'PASS', 'Raw checker did not pass')
    s.require(all(report.get(key) == value for key, value in raw.items()),
              'Stored report differs from independently parsed transcript')
    s.check_result(protocol, report['elf_sha256'], image)
    proof = s.read_json(protocol)
    s.require(proof['log_sha256'] == s.digest(log) and
              proof['vector_trace_sha256'] == s.digest(trace), 'Protocol input drift')
    commands = [s.numeric_fields(line[len('[AKV_PERF] '):], s.PERF_FIELDS)
                for line in log.read_text().splitlines() if line.startswith('[AKV_PERF] ')]
    s.require(len(commands) == (3680 if kind == 'decode' else 13380) and
              s.totals(commands) == raw['raw_hardware_summary'], 'Incomplete command ledger')
    return status, report, raw, pins, image, commands


def audit(run):
    status = s.read_json(run/'status.json')
    kind = status.get('kind')
    s.require(kind in ('decode', 'prefill'), 'Only original real F16 Decode/Prefill fixtures')
    state, candidate, raw_new, pins, image, commands_new = terminal(run, kind)
    s.require(candidate.get('independent_protocol_checked') is True and
              candidate.get('model_execution') is False and
              candidate.get('production_promoted') is False,
              'Wrong candidate evidence class')
    prior = Path(state['prior']).resolve(strict=True)
    s.require(prior != run.resolve() and pins.get(str(prior/'result.json')) ==
              s.digest(prior/'result.json') and pins.get(str(prior/'status.json')) ==
              s.digest(prior/'status.json'), 'Baseline association drift')
    old_state, baseline, raw_old, old_pins, old_image, commands_old = terminal(prior, kind)
    build = Path(state['build']).resolve(strict=True)
    s.require(Path(old_state['build']).resolve() == build and
              candidate['elf_sha256'] == baseline['elf_sha256'], 'Not same build/ELF')
    build_report, baseline_image, _ = original.checked_build(build, kind)
    s.require(build_report['elf_sha256'] == candidate['elf_sha256'] and
              old_image == baseline_image and old_state['simv'] == build_report['simv'],
              'Wrong fixture or original accepted baseline image')
    soc, snapshot, _, accepted_image = checked_soc(Path(state['simv']).parent.parent)
    s.require(image == accepted_image, 'Not the accepted isolated SoC build')
    comparison = compare_runtime(raw_old, raw_new, commands_old, commands_new)
    s.require(candidate.get('matched_baseline') == comparison['matched'],
              'Worker comparison receipt differs')
    s.verify_pins(pins)
    s.verify_pins(old_pins)
    s.verify_pins(candidate['evidence_sha256'])
    s.verify_pins(baseline['evidence_sha256'])
    return dict(state='REAL_RUNTIME_PAIRED_RAW_RECHECKED', kind=kind,
                run=str(run.resolve()), prior=str(prior), same_elf=True,
                elf_sha256=candidate['elf_sha256'], snapshot_sha256=soc['snapshot_sha256'],
                storage_variant=snapshot.get('storage_variant'),
                fixture_scope=raw_new.get('scope'),
                independent_protocol_checked=True, current_inputs_match=True,
                production_promoted=False, ppa_measured=False, model_execution=False,
                comparison=comparison,
                receipts={str(p):s.digest(p) for d in (run, prior) for p in
                          (d/'result.json', d/'status.json', d/'source-pins.json')},
                evidence_sha256=candidate['evidence_sha256'],
                baseline_evidence_sha256=baseline['evidence_sha256'],
                auditor_sha256=s.digest(Path(__file__)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    s.require(not args.output.exists(), 'New output required')
    result = audit(args.run.resolve(strict=True))
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(result['state'], json.dumps(result['comparison'], sort_keys=True))
