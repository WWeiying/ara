#!/usr/bin/env python3
"""Strict standalone gap83 acceptance and same-design raw coverage union."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import coverage_bitmap_delta as bitmap
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification'))
from ara_verify.spike_trace import compare_commit_prefix
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def check_signature(writes):
    # RVFI masks use bus-byte positions; this image's store data is unshifted.
    require(writes.get(0x80002208) == (0x0f, 262) and
            writes.get(0x8000220c) == (0xf0, 0), 'DUT signature missing or failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent.resolve() == ROOT / 'verification/out' and not out.exists(),
            'Independent fresh output required')
    run = ROOT / 'verification/out/gap83-midmant-old-image-20261006-01'
    pre = ROOT / 'verification/out/gap83-midmant-preflight-20261006-01'
    base = ROOT / 'verification/out/gap82-raw-union-689-20261006-01'
    formal = ROOT / 'verification/out/lzc-historical-689-20261006-01'
    load = lambda p: json.loads(p.read_bytes())
    require(load(run / 'simulation-status.json')['status'] == 'SIMULATION_EXITED_NOT_ADMITTED',
            'Simulation did not complete')
    require(load(formal / 'status.json')['status'] == 'RAW_WAIVED_COMPLETE_HISTORICAL_ONLY',
            'Historical baseline incomplete')
    old = load(base / 'combined-bits.json')
    require(len(old['tests']) == 689 and len(set(old['tests'])) == 689, 'Baseline membership differs')
    require((formal / 'inputs.txt').read_text().splitlines()[1:] == old['tests'],
            'Formal/raw baseline member mismatch')
    manifest = load(run / 'manifest.json')
    pins = dict(manifest['pins'])
    for p in [Path(__file__).resolve(), Path(bitmap.__file__), run / 'manifest.json',
              run / 'simulation-status.json', pre / 'spike.trace', base / 'combined-bits.json',
              formal / 'status.json', formal / 'inputs.txt', *run.glob('*.csv'),
              run / 'run.vcs.log', run / 'console.log',
              *sorted((ROOT / 'verification/ara_verify').glob('*.py')),
              *sorted((run / 'code.vdb').rglob('*'))]:
        if p.is_file():
            pins[str(p.resolve())] = sha(p)
    def check():
        for p, h in pins.items():
            require(sha(Path(p)) == h, 'Evidence changed: ' + p)
    check()
    scalar = compare_commit_prefix(pre / 'spike.trace', run / 'commit_trace.csv', 0x80000000,
              terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
    vector = compare_vector_commits(pre / 'spike.trace', run / 'commit_trace.csv',
                                   run / 'vector_trace.csv', 0x80000000)
    require(scalar['status'] == 'TERMINAL_TOHOST_MATCH' and scalar['ara_trap_events'] == 0,
            'Incomplete scalar comparison or trap')
    require(vector['status'] == 'PASS' and vector['compared_instructions'] == 8 and
            vector['compared_bytes'] == 2048 and vector['skipped_unknown_bytes'] == 0 and
            vector['non_bit_exact_instructions'] == 0 and not vector['incomplete_requests'],
            'Incomplete or non-exact vector comparison')
    require([(x['pc'], x['instruction']) for x in vector['instructions']
             if x['instruction'] == '0xc2821857'] ==
            [('0x0000000080002074', '0xc2821857'), ('0x0000000080002114', '0xc2821857')],
            'Target widening request identities differ')
    require(not check_contract_log(run / 'run.vcs.log'), 'Contract violation')
    require((run / 'run.vcs.log').read_text().count('Core Test *** SUCCESS ***') == 1,
            'Missing or repeated software success')
    with (run / 'commit_trace.csv').open() as stream:
        writes = {int(r['mem_addr'], 16): (int(r['mem_wmask'], 16), int(r['mem_wdata'], 16))
                  for r in csv.DictReader(stream) if r['event'] == 'retire' and int(r['mem_wmask'], 16)}
    check_signature(writes)
    check()
    out.mkdir()
    inputs = out / 'new-inputs.txt'
    design = ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
    with inputs.open('x') as stream:
        stream.write(str(design) + '\n' + str(run / 'code.vdb') + '\n')
    new = bitmap.collect(inputs)
    combined = bitmap.combine(old, new)
    delta = bitmap.delta(old, combined)
    check()
    save(out / 'scalar-comparison.json', scalar)
    save(out / 'vector-comparison.json', vector)
    save(out / 'combined-bits.json', combined)
    save(out / 'raw-bitmap-delta.json', delta)
    with (out / 'combined-inputs.txt').open('x') as stream:
        stream.write('\n'.join([str(design), *combined['tests']]) + '\n')
    save(out / 'evidence-pins.json', pins)
    save(out / 'status.json', dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', new_passed=1,
         aggregate_passed=690, official_DVE_report=False, rtl_changed=False,
         simulations_started=False, new_RTL_signoff=False))
    print(json.dumps(dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=690,
                         raw_delta=delta['metrics'])))


if __name__ == '__main__':
    main()
