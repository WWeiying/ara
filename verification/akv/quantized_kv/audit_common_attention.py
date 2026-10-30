#!/usr/bin/env python3
"""Independently accept public-entry timing with its exact decoder comparison."""
import argparse
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from run_common_attention import checked_build, s, HERE, ROOT
from check_common_attention import check_log
from audit_attention import checked_attention
from common_variant import classify


def checked_decoder_comparison(report, symbols):
    comparison = classify(report)
    flags = (report.get('rvv_value_decode', False), report.get('rvv_baseline_decode', False))
    observed = tuple('<' + name + '>:' in symbols for name in
                     ('dequantize_row_q8_0', 'value_rvv_decode', 'fair_value_decode'))
    s.require(observed == {(False, False): (True, False, False),
                           (True, False): (True, True, False),
                           (True, True): (False, False, True)}[flags],
              'Decoder metadata and linked implementations disagree')
    def instructions(name):
        body = symbols.split('<' + name + '>:', 1)[1].split('\n\n', 1)[0]
        return set(re.findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]+\s+([a-z0-9_.]+)', body, re.M))
    if observed[0]:
        scalar = instructions('dequantize_row_q8_0')
        s.require({'fcvt.s.w', 'fmul.s', 'fsw'} <= scalar and not any(op.startswith('v') for op in scalar),
                  'This compiler does not match the recorded scalar production decoder')
    if flags[0]:
        vector = instructions('fair_value_decode' if flags[1] else 'value_rvv_decode')
        s.require({'vle8.v', 'vsext.vf4', 'vfcvt.f.x.v', 'vfmul.vf', 'vse32.v'} <= vector,
                  'Recorded RVV decoder operations absent')
    return comparison


def checked_run(run):
    status, result = s.read_json(run / 'status.json'), s.read_json(run / 'result.json')
    s.require(status.get('state') == result.get('state') == 'PASS' and
              status.get('child_pid') is None and type(result.get('simulator_exit_code')) is int and
              result.get('simulator_exit_code') == 0 and
              result.get('post_pins_match') is True and result.get('independent_protocol_checked') is True,
              'Require complete, checked terminal public-entry PASS')
    report, required = checked_build(Path(status['build']))
    s.require(status.get('elf') == report['elf'] and status.get('simv') == report['simv'] and
              result.get('elf_sha256') == report['elf_sha256'] and
              s.digest(run / 'source-pins.json') == result['source_pins_sha256'], 'Run/build identity drift')
    pins = s.read_json(run / 'source-pins.json')
    s.require(all(pins.get(p) == sha for p, sha in required.items()), 'Run omitted build inputs')
    s.require(pins.get(str(HERE / 'run_common_attention.py')) == s.digest(HERE / 'run_common_attention.py'),
              'Wrong original worker identity')
    s.merge_pins(pins, result['evidence_sha256'])
    s.merge_pins(pins, s.hashes([run / 'status.json', run / 'result.json']))
    s.verify_pins(pins)
    prior = Path(status['prerequisite'])
    old, image, inherited, previous = checked_attention(prior)
    s.require(old['kind'] == report['kind'] and image == report['accepted_image_pins'] and
              Path(report['original_build']) == Path(s.read_json(prior / 'status.json')['build']) and
              all(pins.get(p) == sha for p, sha in inherited.items()), 'Original comparison lineage mismatch')
    prerequisite = s.read_json(run / 'prerequisite-audit.json')
    s.require(prerequisite.get('state') == 'INDEPENDENTLY_REPLAYED' and
              prerequisite.get('result_sha256') == s.digest(prior / 'result.json') and
              prerequisite.get('sums') == previous['sums'] and prerequisite.get('speedup') == previous['speedup'],
              'Incorrect original independent-replay receipt')
    data = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
        'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block'
    log, trace, protocol = (run / 'work' / name for name in ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
    parsed = check_log(log.read_text(), int(report['kind'] == 'q4_0'),
                       (data / 'kqv_out-0.bin').read_bytes(), (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
    s.require(all(result.get(key) == value for key, value in parsed.items()
                  if key not in ('state', 'independent_protocol_checked')), 'Original result differs from raw replay')
    s.check_result(protocol, report['elf_sha256'], image)
    uvm = s.read_json(protocol)
    s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
              'Protocol input hashes differ')
    disassembly = Path(status['build']) / 'disassembly.log'
    s.require(str(disassembly) in report['artifact_sha256'], 'No sealed decoder disassembly')
    comparison = checked_decoder_comparison(report, disassembly.read_text())
    exact_outputs = all(row['output_bits'] == parsed['trials'][0]['output_bits'] for row in parsed['trials'])
    exact_csr = all((row['fcsr'], row['vcsr']) ==
                    (parsed['trials'][0]['fcsr'], parsed['trials'][0]['vcsr']) for row in parsed['trials'])
    accepted = dict(state='INDEPENDENT_COMMON_ATTENTION_ACCEPTED', kind=report['kind'],
                    comparison=comparison, cycles=[row['cycles'] for row in parsed['trials']],
                    sums=parsed['sums'], speedup=parsed['speedup'],
                    cycle_reduction_percent=parsed['cycle_reduction_percent'],
                    benefit_observed=parsed['speedup'] > 1.0,
                    paired_outputs_exact=exact_outputs, paired_csr_exact=exact_csr,
                    max_pair_abs=parsed['max_pair_abs'], native_commands=16,
                    mapping_timed=True, admission_timed=True,
                    backend_allocation_queries_timed=False, whole_model=False,
                    independent_protocol_checked=True, deployment_approved=False,
                    original_worker_result_sha256=s.digest(run / 'result.json'))
    s.merge_pins(pins, s.hashes([Path(__file__), HERE / 'common_variant.py', HERE / 'test_common_variant.py',
                                HERE / 'test_audit_common_attention.py']))
    s.verify_pins(pins)
    return accepted, pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(strict=True), args.output.resolve()
    status = s.read_json(run / 'status.json')
    s.require(not any(out.is_relative_to(Path(p).resolve()) for p in
                     (run, status['build'], status['prerequisite'])), 'Independent output required')
    out.mkdir(parents=True, exist_ok=False)
    try:
        accepted, pins = checked_run(run)
        s.atomic_json(out / 'source-pins.json', pins)
        accepted.update(run=str(run), source_pins_sha256=s.digest(out / 'source-pins.json'), current_inputs_match=True)
        s.atomic_json(out / 'result.json', accepted)
        print('INDEPENDENT_COMMON_ATTENTION_ACCEPTED', accepted['kind'], accepted['speedup'])
    except BaseException as exc:
        s.atomic_json(out / 'result.json', dict(state='FAIL', error=repr(exc)))
        raise


if __name__ == '__main__': main()
