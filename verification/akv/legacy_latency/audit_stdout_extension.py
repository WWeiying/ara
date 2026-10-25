#!/usr/bin/env python3
"""Offline successor: audit one exact post-return stdout extension, never rerun VCS."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('legacy_stdout_frozen_runner', HERE/'run.py')
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)
require = runner.checker.require
digest = runner.tools.digest


def stdout_extension(data, sealed_hash):
    require(data.endswith(b'PASS\n'), 'Not the exact post-return PASS suffix')
    prefix = data[:-5]
    require(hashlib.sha256(prefix).hexdigest() == sealed_hash,
            'Worker stdout prefix does not match original sealed hash')
    require(hashlib.sha256(data).hexdigest() != sealed_hash,
            'Expected the original evidence mismatch')
    return dict(original_prefix_bytes=len(prefix), appended_bytes_hex='504153530a',
                sealed_prefix_sha256=sealed_hash,
                terminal_sha256=hashlib.sha256(data).hexdigest())


def check_evidence(evidence, source):
    worker = str(source/'worker.log')
    require(worker in evidence, 'Missing original worker evidence')
    for mode in ('baseline', 'candidate'):
        for suffix in ('-suite.log', '-compile.log', '-checked.json',
                       '-compile-admission.json', '-suite.exit.json', '-compile.exit.json',
                       '-suite.command.json', '-compile.command.json', '.f', '/simv'):
            require(str(source/(mode+suffix)) in evidence, 'Incomplete original evidence')
    mismatches = []
    for name, expected in evidence.items():
        require(Path(name).is_relative_to(source), 'Evidence outside original output')
        if digest(Path(name)) != expected:
            mismatches.append(name)
    require(mismatches == [worker], 'Expected only worker.log evidence mismatch')
    extension = stdout_extension(Path(worker).read_bytes(), evidence[worker])
    # Preserve the actual original verifier failure, not a fabricated clean PASS.
    try:
        runner.tools.verify(evidence)
    except ValueError as exc:
        require(str(exc) == 'Input identity changed: '+worker, 'Unexpected original verifier failure')
        extension['original_verifier_error'] = str(exc)
    else:
        raise ValueError('Original evidence unexpectedly passed')
    return extension


def audit(source, output, expected_result):
    require(not output.exists() and not output.is_relative_to(source) and
            not source.is_relative_to(output), 'Fresh independent output required')
    require(digest(source/'result.json') == expected_result, 'Original result identity mismatch')
    original = json.loads((source/'result.json').read_text())
    require(original['state'] == 'PASS' and original['schema'] == runner.SCHEMA and
            original['post_pins_match'] is True, 'Original run not terminal semantic PASS')
    require(json.loads((source/'status.json').read_text()) ==
            dict(state='PASS', variant='candidate', child_pid=None), 'Worker not terminal')
    own = [HERE/'audit_stdout_extension.py', HERE/'test_audit_stdout_extension.py',
           Path(sys.executable).resolve()]
    own += [Path(m.__file__).resolve() for m in tuple(sys.modules.values())
            if getattr(m, '__file__', None) and Path(m.__file__).resolve().is_relative_to(runner.ROOT)]
    own_pins = {str(p):digest(p) for p in own}
    original_pins = {str(source/n):digest(source/n)
                     for n in ('result.json', 'status.json', 'manifest.json', 'source-pins.json')}
    manifest = runner.verify_prepared(source, original['manifest_sha256'])
    require(original['source_pins_sha256'] == manifest['source_pins_sha256'], 'Source receipt mismatch')
    extension = check_evidence(original['evidence'], source)
    parsed = {}
    for mode in ('baseline', 'candidate'):
        for phase in ('compile', 'suite'):
            require(json.loads((source/f'{mode}-{phase}.exit.json').read_text()) == {'exit_code':0},
                    'Nonzero/malformed exit receipt')
        admission = runner.check_compile((source/f'{mode}-compile.log').read_text(), 0,
                                         Path(manifest['snapshot'])/runner.TLB_RELATIVE)
        require(admission == manifest['admitted_compile_warning'] ==
                json.loads((source/f'{mode}-compile-admission.json').read_text()), 'Warning admission drift')
        parsed[mode] = runner.checker.check_log((source/f'{mode}-suite.log').read_text(), 0)
        require(parsed[mode] == original[mode] ==
                json.loads((source/f'{mode}-checked.json').read_text()), 'Raw/ledger mismatch')
    compared = runner.checker.compare(parsed['baseline'], parsed['candidate'])
    require(compared['state'] == 'PASS' and compared['commands'] == 892 and
            all(original[k] == v for k,v in compared.items()), 'Original paired comparison mismatch')
    runner.verify_prepared(source, original['manifest_sha256'])
    require(extension == check_evidence(original['evidence'], source), 'Stdout changed during audit')
    runner.tools.verify(original_pins)
    runner.tools.verify(own_pins)
    rows = parsed['baseline']['rows']
    output.mkdir(parents=True)
    report = dict(schema='akv_legacy_latency_stdout_extension_audit_v1',
        state='FUNCTIONAL_AND_LATENCY_AUDIT_PASS', clean_original_evidence=False,
        original_full_evidence_check='FAIL', original_worker_reported_state=original['state'],
        original_output=str(source), original_result_sha256=expected_result,
        source_pins_sha256=original['source_pins_sha256'],
        original_source_header_graph_pins_pre_post_match=True,
        stdout_extension=extension, commands=892, differences=[],
        outcomes=dict(success=sum(r['success'] for r in rows), fault=sum(r['fault'] for r in rows),
                      validation=sum(r['validation'] for r in rows),
                      read_faults={str(k):sum(r['fault'] and r['read_fault_kind']==k for r in rows)
                                   for k in (2,3,5)}),
        cycles_each={k:sum(r[k] for r in rows)
                     for k in ('first_latency','fire_latency','wait_cycles','command_cycles')},
        original_evidence=original['evidence'], audit_source_pins=own_pins,
        original_receipt_pins=original_pins, rerun=False, soc_verified=False,
        model_performance=False, ppa_measured=False, production_promoted=False)
    runner.tools.save(output/'result.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-result-sha256', required=True)
    args = parser.parse_args()
    result = audit(args.input.resolve(strict=True), args.output.resolve(), args.expected_result_sha256)
    print(result['state'])


if __name__ == '__main__':
    main()
