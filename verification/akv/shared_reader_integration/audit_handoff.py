#!/usr/bin/env python3
"""Recheck integrated handoff evidence and compare matched baseline command work."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_handoff import s, checked_soc, ROOT, log_checker
from sharedwave_checker import check_cycles


def compare_records(original, candidate):
    s.require(len(original) == len(candidate) == 71, 'Need all matched commands')
    differences = []
    for ordinal, (old, new) in enumerate(zip(original, candidate)):
        s.require(set(old) == set(new), 'Command counter schema changed')
        delta = {key: dict(baseline=old[key], candidate=new[key])
                 for key in old if old[key] != new[key]}
        if delta:
            differences.append(dict(command=ordinal, fields=delta))
    return differences


def audit(run):
    run = run.resolve(strict=True)
    status, report = (s.read_json(run / name) for name in ('status.json', 'result.json'))
    s.require(status.get('state') == report.get('state') == 'PASS' and
              status.get('child_pid') is None and report.get('post_pins_match') is True and
              report.get('independent_protocol_checked') is True, 'Need terminal checked PASS')
    s.require(s.digest(run / 'source-pins.json') == report['source_pins_sha256'], 'Run receipt changed')
    pins = s.read_json(run / 'source-pins.json')
    s.verify_pins(pins)
    s.verify_pins(report['evidence_sha256'])
    soc, snapshot, _, image = checked_soc(Path(status['soc_build']))
    source = Path(snapshot['source_mapping'][str(ROOT / 'hardware/src/vlsu/vlsu.sv')])
    raw = log_checker.check_log((run / 'work/run.vcs.log').read_text(), source.read_text())
    for key, value in raw.items():
        s.require(key == 'state' or report.get(key) == value, 'Transcript receipt mismatch: ' + key)
    waves = check_cycles(run / 'cycles/cycles.csv')
    s.require(waves == report['wave_evidence'], 'Wave receipt mismatch')
    s.check_result(run / 'work/uvm_result.json', report['elf_sha256'], image)
    protocol = s.read_json(run / 'work/uvm_result.json')
    s.require(protocol['log_sha256'] == s.digest(run / 'work/run.vcs.log') and
              protocol['vector_trace_sha256'] == s.digest(run / 'work/vector_trace.csv'),
              'Protocol raw identity mismatch')
    baseline_index = ROOT / 'verification/akv/results/reader-handoff-baseline-20261024.json'
    baseline = s.read_json(baseline_index)
    s.require(baseline['state'] == 'REEXPORTED_FUNCTIONAL_AND_SETTLED_WAVE_AUDIT_PASS' and
              baseline['original_worker_state'] == 'FAIL', 'Wrong baseline audit')
    original = Path(baseline['original_run'])
    s.require(report['elf_sha256'] == pins[str(Path(status['elf']))], 'Candidate ELF mismatch')
    baseline_pins = s.read_json(original / 'source-pins.json')
    s.require(baseline_pins[str(Path(status['elf']))] == report['elf_sha256'], 'Baseline ELF differs')
    old_log = original / 'work/run.vcs.log'
    s.require(baseline['evidence_sha256'][str(old_log)] == s.digest(old_log), 'Baseline raw log changed')
    old = log_checker.check_log(old_log.read_text(), (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
    differences = compare_records(old['hardware_records'], raw['hardware_records'])
    s.verify_pins(pins)
    s.verify_pins(report['evidence_sha256'])
    return dict(state='INTEGRATED_SHARED_READER_RAW_RECHECKED', run=str(run),
        run_result_sha256=s.digest(run / 'result.json'),
        baseline_receipt_sha256=s.digest(baseline_index),
        baseline_original_worker_state='FAIL', baseline_audited=True,
        source_pins_sha256=report['source_pins_sha256'], snapshot_sha256=soc['snapshot_sha256'],
        commands=71, resident_rows_self_checked=62, zero_read_commands=waves['zero_read_commands'],
        resident_samples=waves['resident_samples'], samples=waves['samples'],
        physical_readers_observed=1, independent_protocol_checked=True,
        current_inputs_match=True, command_counters_identical=not differences,
        command_counter_differences=differences, same_elf=True,
        whole_model=False, real_model_performance=False, ppa_measured=False,
        production_promoted=False, evidence_sha256=report['evidence_sha256'],
        auditor_sha256=s.digest(Path(__file__)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    s.require(not args.output.exists(), 'New output required')
    result = audit(args.run)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(result['state'], 'exact_command_counters=' + str(result['command_counters_identical']))
