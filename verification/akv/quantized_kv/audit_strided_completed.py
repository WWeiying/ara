#!/usr/bin/env python3
"""Recheck a completed strided-cache VCS inquiry without rerunning simulation."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from run_common_attention import s
from check_strided_attention import check_log


def audit(run):
    run = run.resolve(strict=True)
    status = s.read_json(run / 'status.json')
    report = s.read_json(run / 'result.json')
    s.require(status.get('state') == report.get('state') == 'PASS' and
              status.get('child_pid') is None and report.get('post_pins_match') is True,
              'Not checked terminal PASS')
    s.require(report.get('independent_protocol_checked') is True and
              report.get('simulator_exit_code') == 0, 'Missing protocol/exit evidence')
    pins = s.read_json(run / 'source-pins.json')
    s.require(s.digest(run / 'source-pins.json') == report['source_pins_sha256'], 'Pins receipt changed')
    s.verify_pins(pins)
    s.verify_pins(report['evidence_sha256'])
    build = s.read_json(Path(status['build']) / 'build.json')
    kind = status['kind']
    s.require(kind in ('q4_0', 'q8_0') and build['kind'] == kind, 'Wrong profile')
    simv, elf = Path(status['simv']), Path(status['elf'])
    image = build['accepted_image_pins']
    s.require(s.hashes(s.image_files(simv)) == image and
              s.digest(elf) == build['elf_sha256'] == report['elf_sha256'], 'Image/ELF changed')
    data = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
        'capture-k-' + kind + '-v-q8_0') / 'decode/block/kqv_out-0.bin'
    golden_sha = s.digest(data)
    log, trace = run / 'work/run.vcs.log', run / 'work/vector_trace.csv'
    raw = check_log(log.read_text(), int(kind == 'q4_0'), data.read_bytes(),
                    (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
    for key, value in raw.items():
        # The parser deliberately cannot certify protocol checks. The worker
        # sets this only after the independently hashed UVM report is accepted.
        if key not in ('state', 'independent_protocol_checked'):
            s.require(report.get(key) == value, 'Raw result disagreement: ' + key)
    protocol = run / 'work/uvm_result.json'
    s.check_result(protocol, report['elf_sha256'], image)
    p = s.read_json(protocol)
    s.require(p['log_sha256'] == s.digest(log) and
              p['vector_trace_sha256'] == s.digest(trace), 'Protocol input mismatch')
    s.verify_pins(pins)
    s.verify_pins(report['evidence_sha256'])
    s.require(s.digest(data) == golden_sha, 'Golden changed during audit')
    return dict(state='RAW_STRIDED_VCS_RECHECKED', run=str(run), kind=kind,
        source_pins_sha256=report['source_pins_sha256'],
        result_sha256=s.digest(run / 'result.json'),
        status_sha256=s.digest(run / 'status.json'), golden_sha256=golden_sha,
        image_checked=True, current_inputs_match=True, independent_protocol_checked=True,
        speedup=raw['speedup'], sums=raw['sums'],
        cycle_reduction_percent=raw['cycle_reduction_percent'],
        trials=[{k: t[k] for k in ('trial', 'shared', 'cycles', 'fcsr', 'vcsr',
                                  'max_abs', 'pair_bits_differ', 'pair_max_abs')}
                for t in raw['trials']],
        qbs_commands=len(raw['hardware_records']),
        qbs_busy_cycles=sum(r['busy_cycles'] for r in raw['hardware_records']),
        copied_key_bytes=raw['copied_key_bytes'], workspace_bytes=raw['workspace_bytes'],
        whole_model=False, hardware_only=False, deployment_approved=False,
        scope=raw['scope'], evidence_sha256=report['evidence_sha256'],
        auditor_sha256=s.digest(Path(__file__)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Output must not exist')
    result = audit(args.run)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(f"{result['state']} {result['kind']} speedup={result['speedup']:.6f}")
