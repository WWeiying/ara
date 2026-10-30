#!/usr/bin/env python3
"""Offline same-ELF resource audit. No build, simulation, polling or subprocess.

Usage: audit_timed_decode.py --baseline OLD_RUN --unified NEW_RUN --output NEW.json
PASS requires exact command ledgers AND no slower individual native call.
Baseline is full QBS+AKV dual-reader/legacy+v2 storage, NOT ordinary RVV.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TIMED = HERE.parent/'paired_heads/timed_decode'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def frozen_helpers():
    # Frozen files use short local imports. Temporarily bind them to uniquely
    # named instances; do not replace another caller's generic build/run modules.
    names = ('timed_spec', 'build', 'timed_check')
    saved = {name: sys.modules.get(name) for name in names}
    path = list(sys.path)
    try:
        sys.path.insert(0, str(TIMED))
        spec = load('_timed_audit_spec', TIMED/'timed_spec.py')
        sys.modules['timed_spec'] = spec
        build = load('_timed_audit_build', TIMED/'build.py')
        sys.modules['build'] = build
        check = load('_timed_audit_check', TIMED/'timed_check.py')
        sys.modules['timed_check'] = check
        runner = load('_timed_audit_runner', TIMED/'run.py')
        sys.path.insert(0, str(HERE))
        compare = load('_timed_audit_comparison', HERE/'audit_real_runtime.py')
        inventory = load('_timed_audit_inventory', ROOT/'verification/ara_verify/vcs_source_manifest.py')
        return spec, build, check, runner, compare, inventory
    finally:
        sys.path[:] = path
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


spec, builder, checker, worker, comparison_helper, inventory = frozen_helpers()
s = spec.s
SCHEMA = 'timed_decode_resource_pair_audit_v1'
LABELS = dict(baseline='Original full QBS+AKV dual-reader and legacy+v2 storage resource baseline',
              unified='QBS+AKV shared-reader and unified Q2/KV32 storage resource candidate',
              objective='Same-ELF resource integration: exact command counters and no per-call cycle regression',
              ordinary_rvv_comparison=False, acceleration_against_rvv=False)
TRIAL_COUNTS = (197, 84, 197, 774, 373, 774, 137, 137, 137, 386, 98, 386)


def identical(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def helper_pins():
    paths = [Path(__file__), HERE/'test_audit_timed_decode.py', Path(sys.executable).resolve(), *s.script_files()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                paths.append(path)
    return s.hashes(set(paths))


def pin_json(path, pins):
    s.merge_pins(pins, s.hashes([path]))
    return s.read_json(path)


def validate_raw(raw):
    s.require(raw.get('state') == 'PASS' and raw.get('complete_native_call_cycles') is True,
              'Need timed raw functional PASS')
    trials, records, timings = raw['trials'], raw['hardware_records'], raw['timings']
    s.require(len(trials) == len(timings) == 12 and len(records) == 3680, 'Incomplete 12-call/3680-command scope')
    s.require(identical(s.totals(records), raw['raw_hardware_summary']), 'Raw ledger/summary mismatch')
    offset, previous_end = 0, -1
    for index, (trial, timing, count) in enumerate(zip(trials, timings, TRIAL_COUNTS)):
        case, ordinal = divmod(index, 3)
        s.require(set(trial) == {'case', 'trial', 'requested', 'checksum', 'fcsr', 'vcsr', 'hardware_totals', 'cycles'} and
                  type(trial['case']) is int and trial['case'] == case and
                  type(trial['trial']) is int and trial['trial'] == ordinal and
                  type(trial['requested']) is int and trial['requested'] == int(ordinal == 1), 'Trial schema/order drift')
        s.require(type(trial['cycles']) is int and trial['cycles'] > 0, 'Missing/invalid per-call cycles')
        group = records[offset:offset+count]
        offset += count
        s.require(all(set(row) == set(s.PERF_FIELDS) and
                      all(type(v) is int and v >= 0 for v in row.values()) for row in group), 'Command schema/type drift')
        s.require([row['seq'] for row in group] == list(range(offset-count+1, offset+1)), 'Command order drift')
        total = s.totals(group)
        s.require(identical(trial['hardware_totals'], total), 'Per-call command totals mismatch')
        s.require(set(timing) == {'case', 'trial', 'start', 'end', 'cycles', 'command_busy_cycles'} and
                  all(type(v) is int for v in timing.values()) and timing['case'] == case and
                  timing['trial'] == ordinal and 0 <= timing['start'] < timing['end'] < 2**64 and
                  timing['start'] > previous_end and timing['end']-timing['start'] == trial['cycles'] == timing['cycles'] and
                  trial['cycles'] >= timing['command_busy_cycles'] == total['busy_cycles'] > 0,
                  'Timing identity/delta/busy mismatch')
        previous_end = timing['end']


def compare_pair(baseline, unified):
    validate_raw(baseline)
    validate_raw(unified)
    return comparison_helper.compare_runtime(baseline, unified,
        baseline['hardware_records'], unified['hardware_records'])


def check_command(path, argv, cwd, timeout, pins, python=False):
    command = pin_json(path, pins)
    s.require(set(command) == {'argv', 'cwd', 'timeout_seconds'}, 'Unexpected command receipt schema')
    actual = command['argv']
    s.require(type(actual) is list and all(type(x) is str for x in actual) and bool(actual), 'Invalid argv')
    if python:
        executable = Path(actual[0]).resolve(strict=True)
        s.require(pins.get(str(executable)) == s.digest(executable), 'Unpinned Python executable')
        actual = actual[1:]
    s.require(actual == list(map(str, argv)) and command['cwd'] == str(cwd) and
              type(command['timeout_seconds']) is int and command['timeout_seconds'] == timeout,
              'Actual command/image/ELF/checker arguments differ')


def check_manifests(run, simv, pins):
    path = simv.parent/'vcs_source_manifest.json'
    manifest = pin_json(path, pins)
    s.require(manifest.get('schema_version') == 1, 'Source manifest schema')
    prior = {row['path']: row['sha256'] for row in manifest['files']}
    s.require(len(prior) == len(manifest['files']) and bool(prior), 'Empty/duplicate manifest sources')
    current = {row['path']: row['sha256'] for row in inventory.collect(Path(manifest['filelist']),
        Path(manifest['repo_root']), list(map(Path, manifest['extra_sources'])))}
    s.require(current == prior and all(pins.get(p) == sha for p, sha in prior.items()), 'Source inventory changed/unpinned')
    for stage in ('manifest-before', 'manifest-after'):
        result = pin_json(run/(stage+'.log'), pins)
        s.require(set(result) == {'status', 'file_count', 'changed'} and result['status'] == 'PASS' and
                  type(result['file_count']) is int and result['file_count'] == len(prior) and
                  result['changed'] == [], 'Pre/post source manifest check failed')
        check_command(run/(stage+'.command.json'), ['-B', '-m', 'ara_verify.vcs_source_manifest',
            '--output', path, '--check'], run, 300, pins, python=True)


def terminal(run, variant, cache):
    pins = {}
    status = pin_json(run/'status.json', pins)
    report = pin_json(run/'result.json', pins)
    s.require(status.get('state') == report.get('state') == 'PASS' and
              'child_pid' in status and status['child_pid'] is None and
              status.get('kind') == report.get('kind') == 'timed_decode' and status.get('variant') == variant,
              'Need terminal timed Decode PASS of requested variant')
    for key in ('running_exit_code', 'checking_exit_code', 'manifest-before_exit_code',
                'manifest-after_exit_code', 'image_contract_exit_code'):
        s.require(type(status.get(key)) is int and status[key] == 0, 'Missing/failed worker phase '+key)
    s.require(type(report.get('simulator_exit_code')) is int and report['simulator_exit_code'] == 0 and
              report.get('post_pins_match') is True and report.get('independent_protocol_checked') is True and
              report.get('model_execution') is False and report.get('production_promoted') is False and
              report.get('complete_operator_performance_accepted') is False, 'Wrong evidence class')
    source_receipt = run/'source-pins.json'
    saved = pin_json(source_receipt, pins)
    s.require(s.digest(source_receipt) == report['source_pins_sha256'], 'Worker source receipt drift')
    s.merge_pins(pins, saved)
    s.merge_pins(pins, report['evidence_sha256'])
    s.verify_pins(pins)
    build = Path(status['build']).resolve(strict=True)
    if build not in cache:
        cache[build] = builder.checked_build(build)
    build_report, old_image, build_pins = cache[build]
    s.require(all(saved.get(p) == h for p, h in build_pins.items()), 'Worker lacks checked timed build pins')
    identity = status['image_identity']
    soc = Path(identity['soc_build']) if variant == 'unified' else None
    simv, image, selected_pins, expected_identity = worker.select_image(
        SimpleNamespace(variant=variant, soc_build=soc), build_report, old_image)
    s.require(identical(identity, expected_identity) and identical(report['image_identity'], expected_identity) and
              status['simv'] == str(simv) and status['elf'] == build_report['elf'] and
              report['elf_sha256'] == build_report['elf_sha256'], 'Run/build/selected image identity differs')
    s.require(all(saved.get(p) == h for p, h in selected_pins.items()), 'Worker lacks accepted image pins')
    s.merge_pins(pins, selected_pins)
    s.merge_pins(pins, build_pins)
    s.require(s.hashes(s.image_files(simv)) == image, 'Actual image inventory differs')
    elf = Path(status['elf'])
    s.require(saved.get(str(elf)) == report['elf_sha256'] == s.digest(elf), 'ELF identity drift')
    for file in (TIMED/'timed_spec.py', TIMED/'build.py', TIMED/'timed_check.py', TIMED/'run.py'):
        s.require(saved.get(str(file)) == s.digest(file), 'Frozen worker/helper not pinned')
    work = run/'work'
    log, trace, protocol = (work/name for name in ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
    required = (log, trace, protocol, source_receipt, run/'manifest-before.log', run/'manifest-after.log',
                run/'image-contract.log', work/'console.command.json', work/'checker.command.json')
    s.require(all(str(p) in report['evidence_sha256'] for p in required), 'Missing raw/protocol evidence')
    raw = checker.check_log(log.read_text())
    validate_raw(raw)
    s.require(all(k in report and identical(report[k], v) for k, v in raw.items()), 'Stored/raw result mismatch')
    timeout = status['timeout_seconds']
    s.require(type(timeout) is int and 1 <= timeout <= 10800, 'Unbounded simulator')
    check_command(work/'console.command.json', [simv, '-no_save', '-l', log, '+PRELOAD='+str(elf),
        '+TESTCASE=akv_timed_decode_'+variant, '+NO_FSDB', '+NO_INSTR_TRACE', '+AKV_PERF', '+AKV_SUMMARY',
        '+VECTOR_TRACE='+str(trace), '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
        work, timeout, pins)
    check_command(work/'checker.command.json', ['-B', '-m', 'ara_verify.uvm_dut', '--require-events',
        '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log,
        '--simv', simv, '--elf', elf, '--output', protocol], work, 600, pins, python=True)
    check_command(run/'image-contract.command.json', ['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
        simv.parent, elf, 'akv_v2'], run, 180, pins)
    s.check_result(protocol, report['elf_sha256'], image)
    proof = s.read_json(protocol)
    s.require(proof['log_sha256'] == s.digest(log) and proof['vector_trace_sha256'] == s.digest(trace), 'UVM input drift')
    check_manifests(run, simv, pins)
    s.verify_pins(pins)
    return dict(run=str(run), build=str(build), elf=str(elf), elf_sha256=report['elf_sha256'],
                image_identity=expected_identity, image=image, simv=str(simv), raw=raw, pins=pins,
                evidence_sha256=report['evidence_sha256'])


def audit(baseline, unified):
    baseline, unified = baseline.resolve(strict=True), unified.resolve(strict=True)
    s.require(baseline != unified, 'Need distinct baseline/unified runs')
    audit_pins = helper_pins()
    s.verify_pins(audit_pins)
    cache = {}
    old, new = terminal(baseline, 'baseline', cache), terminal(unified, 'unified', cache)
    s.require(old['build'] == new['build'] and old['elf'] == new['elf'] and
              old['elf_sha256'] == new['elf_sha256'], 'Not the same timed build/ELF')
    result = dict(schema=SCHEMA, labels=LABELS, baseline=old, unified=new, same_elf=True,
                  production_promoted=False, model_execution=False, ppa_measured=False,
                  complete_operator_performance_accepted=False)
    try:
        comparison = compare_pair(old['raw'], new['raw'])
        accepted = (comparison['resource_regression_gate_pass'] is True and
                    comparison['complete_operator_performance_accepted'] is True)
        result.update(state='PASS' if accepted else 'REGRESSION', comparison=comparison,
                      complete_operator_performance_accepted=accepted)
    except ValueError as exc:
        # Retain both complete raw ledgers even when the paired numerical/schema
        # comparison rejects. A failed comparison is never a performance PASS.
        result.update(state='FAIL', comparison_error=str(exc))
    for record in (old, new):
        s.verify_pins(record['pins'])
        s.require(s.hashes(s.image_files(Path(record['simv']))) == record['image'], 'Post-audit image drift')
        check_manifests(Path(record['run']), Path(record['simv']), record['pins'])
        s.verify_pins(record['pins'])
    s.verify_pins(audit_pins)
    result.update(audit_source_pins=audit_pins, post_pins_match=True, independent_protocol_checked=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--unified', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    s.require(not args.output.exists(), 'New output required')
    s.require(not any(args.output.resolve().is_relative_to(path.resolve())
                      for path in (args.baseline, args.unified)), 'Keep output outside immutable runs')
    try:
        result = audit(args.baseline, args.unified)
    except Exception as exc:
        result = dict(state='FAIL', schema=SCHEMA, error=repr(exc), labels=LABELS,
                      production_promoted=False, model_execution=False, ppa_measured=False,
                      complete_operator_performance_accepted=False)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(result['state'])
    return 0 if result['state'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
