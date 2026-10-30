#!/usr/bin/env python3
"""Independently recheck canonical-runtime execution, not just its PASS label."""
import argparse
from pathlib import Path

import attention_run as s
from run_live_regression import checked_build, checker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REFERENCES = {
    'decode': dict(
        result=ROOT/'verification/out/akv-native-pair-document-audit-20261024-01/result.json',
        sha256='e92c296827c4033b519f38ba4ef74f65853b9a41022ada5eea1bd0af0e0d732f',
        state='FUNCTIONAL_ACCEPTED_DOCUMENT_ONLY_DRIFT',
        log=ROOT/'verification/out/akv-native-pair-runtime-20261024-01/work/run.vcs.log'),
    'prefill': dict(
        result=ROOT/'verification/out/akv-prefill-pv-slice-20261024-01/result.json',
        sha256='92e28a75bc151590e2f733785b62b2f46002cb01215e76b91c633f577fc78d45',
        state='PASS',
        log=ROOT/'verification/out/akv-prefill-pv-slice-20261024-01/work/run.vcs.log'),
}


def numerical_signature(trials, kind):
    fields = ('case', 'trial', 'requested', 'checksum', 'fcsr', 'vcsr') if kind == 'decode' else (
        'trial', 'paired', 'checksum', 'fcsr', 'vcsr')
    return [{key:t[key] for key in fields} for t in trials]


def audit(run, out):
    run, out = run.resolve(strict=True), out.resolve()
    s.require(not out.is_relative_to(run), 'Independent fresh audit directory required')
    out.mkdir(parents=True, exist_ok=False)
    try:
        status, result = s.read_json(run/'status.json'), s.read_json(run/'result.json')
        kind = status.get('kind')
        s.require(kind in REFERENCES and status.get('state') == result.get('state') == 'PASS' and
                  status.get('child_pid') is None and result.get('kind') == kind and
                  result.get('canonical_runtime') is True and result.get('post_pins_match') is True and
                  result.get('simulator_exit_code') == 0 and
                  all(status.get(key) == 0 for key in ('running_exit_code', 'checking_exit_code',
                      'manifest-before_exit_code', 'manifest-after_exit_code', 'image_contract_exit_code')),
                  'Not a checked terminal canonical-runtime execution')
        build = Path(status['build']).resolve(strict=True)
        report, image, build_pins = checked_build(build, kind)
        s.require(status['simv'] == report['simv'] and status['elf'] == report['elf'] and
                  result['elf_sha256'] == report['elf_sha256'], 'Build/ELF/image mismatch')
        s.require(s.digest(run/'source-pins.json') == result['source_pins_sha256'], 'Worker receipt drift')
        pins = s.read_json(run/'source-pins.json')
        s.require(all(pins.get(path) == sha for path, sha in build_pins.items()), 'Worker omitted build input')
        s.merge_pins(pins, result['evidence_sha256'])
        log, trace, protocol = (run/'work'/name for name in ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
        s.require(all(str(path) in result['evidence_sha256'] for path in (log, trace, protocol)),
                  'Missing raw/protocol evidence')
        s.verify_pins(pins)
        parsed = checker(kind)(log.read_text())
        s.require(all(result.get(key) == value for key, value in parsed.items()), 'Raw transcript/result differs')
        s.check_result(protocol, report['elf_sha256'], image)
        uvm = s.read_json(protocol)
        s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
                  'Independent protocol checker input identity differs')
        reference = REFERENCES[kind]
        s.require(s.digest(reference['result']) == reference['sha256'], 'Historical comparison receipt changed')
        old_result = s.read_json(reference['result'])
        s.require(old_result['state'] == reference['state'] and
                  old_result['evidence_sha256'].get(str(reference['log'])) == s.digest(reference['log']),
                  'Historical raw comparison log not fixed by its original receipt')
        old_parsed = checker(kind)(reference['log'].read_text())
        s.require(numerical_signature(old_parsed['trials'], kind) == numerical_signature(old_result['trials'], kind) ==
                  numerical_signature(parsed['trials'], kind), 'Pre-promotion/post-promotion numerical signature differs')
        s.merge_pins(pins, s.hashes([Path(__file__), HERE/'test_audit_live_regression.py', run/'status.json',
            run/'result.json', run/'source-pins.json', reference['result'], reference['log']]))
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json', pins)
        checked = dict(parsed)
        checked.update(state='CANONICAL_RTL_INDEPENDENTLY_ACCEPTED', kind=kind, run=str(run),
            elf_sha256=report['elf_sha256'], source_pins_sha256=s.digest(out/'source-pins.json'),
            current_inputs_match=True, original_result_unchanged=True, independent_protocol_checked=True,
            reference_state=reference['state'], reference_result_sha256=reference['sha256'],
            historical_numerical_signature_exact=True, historical_current_source_pins_reused=False,
            historical_scope='Numerical comparison only; historical source identities are not asserted to equal current source',
            evidence_sha256=s.hashes([run/'status.json', run/'result.json', log, trace, protocol]),
            model_execution=False)
        s.atomic_json(out/'result.json', checked)
        print('CANONICAL_RTL_INDEPENDENTLY_ACCEPTED kind='+kind)
        return checked
    except BaseException as exc:
        s.atomic_json(out/'result.json', dict(state='FAIL', error=repr(exc)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.run, args.output)


if __name__ == '__main__':
    main()
