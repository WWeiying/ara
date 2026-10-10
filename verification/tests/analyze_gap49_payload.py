#!/usr/bin/env python3
"""Reduce gap40 witnesses without simulating RTL or claiming coverage gains."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / 'verification/out/gap40-custom-analysis-20261004-01'
EXPR = re.compile(r'gen_write_merge\[(\d)\]\.gen_bank_plane\[(\d)\]\.'
                  r'gen_bank_row\[(\d)\]\.gen_byte_merge\[(\d+)\]\.byte_valid')
RTL = ['hardware/include/qbs_pkg.sv', 'hardware/src/ara_dispatcher.sv',
       *['hardware/src/vlsu/qbs/' + n + '.sv' for n in
         ('qbs_descriptor_decoder', 'qbs_engine', 'qbs_read_engine',
          'qbs_compute_engine', 'qbs_block_adapter', 'qbs_payload_buffer')]]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze():
    old_pins = read(HISTORY / 'payload-input-hashes.json')
    sources = [ROOT / p for p in RTL]
    for path in sources:
        if sha(path) != old_pins[str(path)]:
            raise ValueError('RTL differs from witness analysis: ' + str(path))
    points = [p for p in read(HISTORY / 'payload-classification.json')
              if p['classification'].startswith('REACHABLE_')]
    if len(points) != 52:
        raise ValueError('expected exactly 52 reviewed points')
    routing = read(HISTORY / 'payload-routing-evidence.json')
    candidates = {}
    for scenario in routing['scenarios']:
        hits = {tuple(h) for h in scenario['hits']}
        covered = set()
        for i, point in enumerate(points):
            match = EXPR.fullmatch(point['expressions'][0]['exprstr'])
            bank = int(re.search(r'bank(\d)', point['scope'])[1])
            if match and (scenario['kind'] == 'weight' or scenario['bank'] == bank):
                if tuple(map(int, match.groups())) in hits:
                    covered.add(i)
        if covered:
            candidates.setdefault(frozenset(covered),
                                  {k: v for k, v in scenario.items() if k != 'hits'})
    maximal = [s for s in candidates if not any(s < t for t in candidates)]
    universe = set().union(*maximal)
    solution = None
    for count in range(1, len(maximal) + 1):
        solution = next((sets for sets in itertools.combinations(maximal, count)
                         if set().union(*sets) == universe), None)
        if solution:
            break
    selected = [i for i, p in enumerate(points) if p['witness'].get('profile') == 'Q5_K']
    if len(universe) != 44 or len(solution) != 5 or len(selected) != 16:
        raise ValueError('routing-set reduction changed')
    sources += [HISTORY / n for n in ('payload-classification.json',
                'payload-routing-evidence.json', 'payload_analysis.py', 'payload-input-hashes.json')]
    sources += [Path(__file__).resolve(), ROOT / 'apps/common/qbs_abi.h']
    return {
        'status': 'STATIC_LEGALITY_AND_ROUTING_MODEL_NOT_RTL_PASS',
        'simulations_started': False, 'measured_gain': None,
        'reachable_points': len(points), 'stream_points': len(universe),
        'side_metadata_points': 8, 'minimum_stream_scenarios_in_supplied_universe': len(solution),
        'stream_scenarios': [dict(candidates[s], point_ids=sorted(s)) for s in solution],
        'side_scenario': {'profile': 'Q2_K', 'layout': 'ROW_MAJOR', 'rows': 4,
                          'range_base_mod16': 0, 'command_minimum_n': 8,
                          'point_ids': [i for i in range(52) if i not in universe]},
        'single_k_block_cover_commands': [
            dict(weight='Q5_K', activation='Q8_K', weight_layout='ROW_MAJOR',
                 activation_layout='ROW_MAJOR', m=4, n=7, k_blocks=1, w_mod16=2, a_mod16=4),
            dict(weight='Q2_K', activation='Q8_K', weight_layout='ROW_MAJOR',
                 activation_layout='ROW_MAJOR', m=3, n=8, k_blocks=1, w_mod16=0, a_mod16=8),
            dict(weight='Q5_K', activation='Q8_K', weight_layout='ROW_MAJOR',
                 activation_layout='ROW_MAJOR', m=2, n=1, k_blocks=1, w_mod16=2, a_mod16=12),
            dict(weight='Q5_K', activation='Q8_K', weight_layout='ROW_MAJOR',
                 activation_layout='M8', m=5, n=1, k_blocks=1, w_mod16=2, a_mod16=4)],
        'selected': {'name': 'app:qbs_gap49_payload_skew', 'weight': 'Q5_K',
                     'activation': 'Q8_K', 'weight_layout': 'ROW_MAJOR',
                     'activation_layout': 'ROW_MAJOR', 'activation_access': 'DIRECT',
                     'm': 1, 'n': 7, 'k_blocks': 1, 'k_elements': 256,
                     'weight_base_mod16': 2, 'activation_base_mod16': 0,
                     'descriptor_alignment': 16, 'timeout_s': 600,
                     'custom_commands': 1, 'point_ids': selected,
                     'weight_bytes': 1232, 'activation_bytes': 292},
        'points': [dict(id=i, **{k: p[k] for k in ('scope', 'coordinate', 'raw_index',
                   'metric', 'metric_checksum', 'point_checksum', 'classification', 'witness')})
                   for i, p in enumerate(points)],
        'limits': [
            'Minimum is over supplied one-phase routing scenarios, not arbitrary multi-K programs.',
            'Four combined commands realize six families with K=1; they are not implemented here.',
            'M8 storage is eight contexts even at M=5; padded contexts are physically routed.',
            'Bank1 weight local row2 requires N>=7; K advancement resets the active bank to zero.',
            '52-point full cover is outside the requested M1-only app; only 16 targets are selected.',
            'Continuous-input recurrence permits the writes; actual timing/gains require later RTL evidence.'],
        'source_hashes': {str(p): sha(p) for p in sorted(sources)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = analyze()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('STATIC ONLY: 6 routing families; selected M1 N7 K1 Q5_K, 16 potential points')


if __name__ == '__main__':
    main()
