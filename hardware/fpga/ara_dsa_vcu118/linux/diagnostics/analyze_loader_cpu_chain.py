#!/usr/bin/env python3
"""Audit the full-pipeline counterfactual without claiming a board waveform.

Requires pyvcd==0.4.1. Convert each bounded run_0.fsdb with fsdb2vcd first.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def run_result(text, returncode, target):
    retirements = [int(pc, 16) for pc in re.findall(r'^RETIRE cycle=\d+ pc=([0-9a-f]+)$', text, re.M)]
    lost = [dict(cycle=int(cycle), last=int(last), data=hex(int(data, 16)))
            for cycle, last, data in re.findall(
                r'^COLLISION cycle=(\d+) last=([01]) rdata=([0-9a-f]+) '
                r'inval_addr=[0-9a-f]+ capture=0 pop=0$', text, re.M)]
    passed = (returncode == 0 and 'Fatal:' not in text and 'Error:' not in text
              and 'LOADER_CPU_REACHED_TARGET' in text and target in retirements)
    return dict(target_reached=passed, last_retired_pc=hex(retirements[-1]) if retirements else None,
                lost_responses=lost, bounded_stop='LOADER_CPU_BOUNDED_STOP' in text)


def low_phase_samples(path):
    from vcd.reader import TokenKind as K, tokenize
    names, state, time = {}, {}, 0
    with path.open('rb') as stream:
        for token in tokenize(stream):
            if token.kind == K.TIMESCALE:
                if token.timescale.magnitude.value != 1 or token.timescale.unit.value != 'ps':
                    raise ValueError('Expected 1 ps waveform time units')
            elif token.kind == K.VAR:
                name = token.var.reference
                if name in names.values():
                    raise ValueError('Expected only the focused trace scope')
                names[token.var.id_code] = name
            elif token.kind == K.CHANGE_TIME:
                # Values settled in the low clock phase precede the next AXI
                # sampling edge. Post-edge values can already describe another beat.
                if state.get('clk') == 0 and state.get('rst') == 1:
                    yield dict(time_ps=time, **state)
                time = token.time_change
            elif token.kind in (K.CHANGE_SCALAR, K.CHANGE_VECTOR):
                change = token.scalar_change if token.kind == K.CHANGE_SCALAR else token.vector_change
                value = change.value
                state[names[change.id_code]] = int(value) if value in ('0', '1') else value
        if state.get('clk') == 0 and state.get('rst') == 1:
            yield dict(time_ps=time, **state)


def check_inputs(original, corrected):
    hashes = {}
    for name in ('memory.hex', 'boot.bin', 'loader_board_cfg.svh'):
        data = [(directory/name).read_bytes() for directory in (original, corrected)]
        if data[0] != data[1]:
            raise ValueError('Different experimental input: ' + name)
        hashes[name] = hashlib.sha256(data[0]).hexdigest()
    sources = [json.loads((directory/'sources.json').read_text()) for directory in (original, corrected)]
    if sources[0]['original'] != sources[1]['original']:
        raise ValueError('Frozen package source hashes differ')
    adapters = []
    for source, basename in zip(sources, ('wt_axi_adapter.sv', 'wt_axi_adapter_candidate.sv')):
        matches = [path for path in source['compiled'] if Path(path).name == basename]
        if len(matches) != 1:
            raise ValueError('Expected one compiled cache adapter')
        path = Path(matches[0])
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['compiled'][str(path)]:
            raise ValueError('Compiled adapter source changed since simulation')
        adapters.append(path.read_text())
    old, new = 'axi_rd_rdy        = ~invalidate;', 'axi_rd_rdy        = ~invalidate & ~inval_valid_i;'
    if adapters[0].count(old) != 1 or adapters[0].replace(old, new) != adapters[1]:
        raise ValueError('DUT difference is not the single read-ready repair')
    compiled = [Counter(source['compiled'].values()) for source in sources]
    for i in range(2):
        digest = hashlib.sha256(adapters[i].encode()).hexdigest()
        compiled[i].subtract([digest])
    if +compiled[0] != +compiled[1]:
        raise ValueError('Other compiled sources differ')
    return hashes


def audit(original, corrected):
    hashes = check_inputs(original, corrected)
    fixture = json.loads((original/'fixture_summary.json').read_text())
    target = int(fixture['jal_target'], 16)
    last = int(fixture['loader_base'], 16) + int(fixture['loader_pc_offset'], 16)
    results, waves = [], []
    for directory in (original, corrected):
        recorded = json.loads((directory/'results.json').read_text())[0]
        if recorded['collision_schedule'] != 0:
            raise ValueError('Natural timing experiment required')
        text = (directory/'run_0.log').read_text()
        if not re.search(r'^CONTROLLED_INITIAL_STATE .* collision=0 ', text, re.M):
            raise ValueError('Natural timing marker missing')
        results.append(run_result(text, recorded['exit_code'], target))
        waves.append(list(low_phase_samples(directory/'run_0.vcd')))
    old, fixed = results
    lost = [row for row in waves[0] if row['inval'] == row['rvalid'] == row['rready'] == 1
            and row['capture'] == 0 and row['metadata_pop'] == 0]
    blocked = [row for row in waves[1] if row['inval'] == row['rvalid'] == 1 and row['rready'] == 0]
    waits = [row for row in waves[0] if row['cycle'] >= 500 and row['last_pc'] == last
             and row['fetch_va'] == target and row['mshr'] == row['fetch_request'] == 1
             and row['fetch_valid'] == row['rvalid'] == row['ptw_reply'] == 0]
    ack = [row for row in waves[1] if row['ptw_reply'] == 1 and row['cycle'] > 286]
    confirmed = (old['bounded_stop'] and old['last_retired_pc'] == hex(last)
                 and not old['target_reached'] and any(row['rlast'] for row in lost)
                 and len(waits) >= 1000 and fixed['target_reached']
                 and not fixed['lost_responses'] and bool(blocked) and bool(ack))
    return dict(simulated_causal_chain_confirmed=confirmed,
                board_fault_cycle_captured=False,
                scope='Real loader bytes/PTEs, full frozen CPU/Ara, controlled RAM and reset state; not historical board timing',
                matching_last_retired_pc=hex(last), target_pc=hex(target), identical_input_sha256=hashes,
                original=old, corrected=fixed, original_lost_response_samples=lost,
                corrected_backpressure_samples=blocked,
                original_stalled_low_phase_samples=len(waits),
                sample_convention='low phase after cycle N precedes handshake at cycle N+1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('corrected', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.original, args.corrected)
    with args.out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['simulated_causal_chain_confirmed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
