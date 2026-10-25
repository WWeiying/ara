#!/usr/bin/env python3
"""Offline same-ELF quantized Attention resource audit, not algorithm speedup."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit_real_runtime as f16_audit
from run_real_runtime import s, ROOT, checked_soc, compare_outputs
sys.path.insert(0, str(HERE.parent / 'quantized_kv'))
import run_strided_attention as quant

ORDER = (0, 1, 1, 0)


def compare(old, new):
    for raw in (old, new):
        s.require(len(raw['trials']) == 4 and
                  [(t['trial'], t['shared']) for t in raw['trials']] == list(enumerate(ORDER)),
                  'Wrong complete ABBA calls')
        records = raw['hardware_records']
        s.require(len(records) == 16 and [r['seq'] for r in records] == list(range(1, 17)),
                  'Wrong QBS command ledger')
    matched = compare_outputs(old, new)
    commands = f16_audit.compare_commands(old['hardware_records'], new['hardware_records'])
    calls = []
    for index, (before, after) in enumerate(zip(old['trials'], new['trials'])):
        s.require(type(before['cycles']) is type(after['cycles']) is int and
                  before['cycles'] > 0 and after['cycles'] > 0, 'Invalid full-call cycles')
        start, stop = {0:(0, 0), 1:(0, 8), 2:(8, 16), 3:(16, 16)}[index]
        equal = old['hardware_records'][start:stop] == new['hardware_records'][start:stop]
        calls.append(dict(trial=index, shared=ORDER[index], baseline_cycles=before['cycles'],
            candidate_cycles=after['cycles'], cycle_delta=after['cycles']-before['cycles'],
            qbs_commands=stop-start, command_records_identical=equal))
    passed = commands['identical'] and all(c['cycle_delta'] <= 0 for c in calls)
    return dict(state='PASS' if passed else 'REGRESSION', matched=matched, calls=calls,
        command_comparison=commands, resource_regression_gate_pass=passed,
        per_call_cycles_identical=all(c['cycle_delta'] == 0 for c in calls),
        per_call_records_identical=all(c['command_records_identical'] for c in calls))


def terminal(run, kind, build, checker, image, candidate):
    status, report = (s.read_json(run/name) for name in ('status.json', 'result.json'))
    expected_kind = 'quant_'+kind if candidate else kind
    s.require(status.get('state') == report.get('state') == 'PASS' and
              'child_pid' in status and status['child_pid'] is None and
              status.get('running_exit_code') == 0 and status.get('checking_exit_code') == 0 and
              status.get('kind') == expected_kind and report.get('post_pins_match') is True and
              report.get('independent_protocol_checked') is True, 'Not terminal checked quantized PASS')
    if candidate:
        s.require(report.get('kind') == expected_kind and
                  status.get('counter_policy') == 'QBS_PERF_ONLY_NO_AKV_SUMMARY' and
                  report.get('model_execution') is False and report.get('production_promoted') is False,
                  'Wrong candidate counter policy/scope')
    else:
        s.require(report.get('simulator_exit_code') == 0, 'Baseline simulator exit missing')
    s.require(status.get('build') == str(build) and
              s.digest(run/'source-pins.json') == report.get('source_pins_sha256'), 'Build/source receipt drift')
    pins = s.read_json(run/'source-pins.json')
    s.verify_pins(pins)
    evidence = report['evidence_sha256']
    s.verify_pins(evidence)
    elf, simv = Path(status['elf']), Path(status['simv'])
    s.require(pins.get(str(elf)) == report.get('elf_sha256') == s.digest(elf) and
              s.hashes(s.image_files(simv)) == image and
              all(pins.get(p) == h for p, h in image.items()), 'ELF/image binding drift')
    log, trace, protocol = (run/'work'/name for name in
                           ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
    s.require(all(str(p) in evidence for p in (log, trace, protocol)), 'Missing raw/UVM evidence')
    raw = checker(log.read_text())
    s.require(raw['state'] == 'STRIDED_ATTENTION_NUMERICAL_AND_WORK_CHECKED', 'Wrong raw checker')
    s.require(all(report.get(k) == v for k, v in raw.items()
                  if k not in ('state', 'independent_protocol_checked')), 'Stored result/raw mismatch')
    s.check_result(protocol, report['elf_sha256'], image)
    proof = s.read_json(protocol)
    s.require(proof['log_sha256'] == s.digest(log) and proof['vector_trace_sha256'] == s.digest(trace),
              'UVM input identity drift')
    s.require(proof.get('contract_event_count', 0) > 0 and proof.get('uvm_backend_event_count', 0) > 0 and
              proof.get('axi_read_counts', {}).get('completed', 0) > 0 and
              proof.get('axi_write_counts', {}).get('matched', 0) > 0, 'Incomplete UVM scope')
    s.merge_pins(pins, evidence)
    s.merge_pins(pins, s.hashes([run/n for n in ('status.json', 'result.json', 'source-pins.json')]))
    return status, report, raw, pins


def audit(run):
    own = [Path(__file__), HERE/'test_audit_real_quantized.py', Path(sys.executable).resolve()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().is_relative_to(ROOT): own.append(Path(name).resolve())
    own_pins = s.hashes(own)
    state = s.read_json(run/'status.json')
    s.require(state.get('kind') in ('quant_q4_0', 'quant_q8_0'), 'Only quantized strided Attention')
    kind = state['kind'].removeprefix('quant_')
    build, prior = (Path(state[k]).resolve(strict=True) for k in ('build', 'prior'))
    s.require(prior != run, 'Self baseline forbidden')
    report, pins = quant.checked_build(build)
    s.require(report['kind'] == kind and state['elf'] == report['elf'], 'Wrong profile/ELF')
    capture = ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'/(
        'capture-k-'+kind+'-v-q8_0')/'decode/block/kqv_out-0.bin'
    rtl = ROOT/'hardware/src/vlsu/vlsu.sv'
    s.require(pins.get(str(capture)) == s.digest(capture) and pins.get(str(rtl)) == s.digest(rtl),
              'Unpinned golden or QBS counter schema')
    golden, rtl_text = capture.read_bytes(), rtl.read_text()
    def checker(text):
        return quant.check_log(text, int(kind == 'q4_0'), golden, rtl_text)
    soc_dir = Path(state['simv']).parent.parent
    soc, snapshot, soc_pins, image = checked_soc(soc_dir)
    s.require(soc['simv'] == state['simv'], 'Wrong isolated image')
    old_state, baseline, old, old_pins = terminal(prior, kind, build, checker,
                                                 report['accepted_image_pins'], False)
    new_state, candidate, new, new_pins = terminal(run, kind, build, checker, image, True)
    s.require(old_state['simv'] == report['simv'] and old_state['elf'] == report['elf'] and
              baseline['elf_sha256'] == candidate['elf_sha256'] == report['elf_sha256'],
              'Not same accepted baseline build/ELF')
    s.require(all(new_pins.get(str(prior/n)) == s.digest(prior/n) for n in ('result.json', 'status.json')),
              'Candidate baseline association not pinned')
    comparison = compare(old, new)
    s.require(candidate['matched_baseline'] == comparison['matched'], 'Worker comparison differs')
    for inventory in (soc_pins, old_pins, new_pins): s.merge_pins(pins, inventory)
    s.merge_pins(pins, own_pins)
    s.verify_pins(pins)
    return dict(state=comparison['state'], acceptance='QUANTIZED_SAME_ELF_RESOURCE_RAW_RECHECKED',
        kind=kind, run=str(run), prior=str(prior), elf_sha256=report['elf_sha256'], same_elf=True,
        baseline_image=report['simv'], candidate_image=state['simv'],
        snapshot_sha256=soc['snapshot_sha256'], storage_variant=snapshot.get('storage_variant'),
        comparison=comparison, independent_protocol_checked=True, current_inputs_match=True,
        scope='Same-ELF corresponding calls: original dual-reader image versus isolated shared-reader image; '
              'quantized head-major versus shared schedule speedup is NOT a reader benefit',
        whole_model_performance=False, pure_hardware_speedup_claim=False,
        production_promoted=False, ppa_measured=False,
        receipt_pins={str(d/n):s.digest(d/n) for d in (run, prior) for n in
                      ('result.json', 'status.json', 'source-pins.json')},
        auditor_sha256=s.digest(Path(__file__))), pins


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    s.require(not args.output.exists(), 'Fresh audit output required')
    result, pins = audit(args.run.resolve(strict=True))
    args.output.mkdir(parents=True, exist_ok=False)
    s.atomic_json(args.output/'source-pins.json', pins)
    result['source_pins_sha256'] = s.digest(args.output/'source-pins.json')
    s.atomic_json(args.output/'result.json', result)
    print(result['state'], json.dumps(result['comparison']['calls']))
    sys.exit(0 if result['state'] == 'PASS' else 1)
