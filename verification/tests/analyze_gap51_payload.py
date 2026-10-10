#!/usr/bin/env python3
"""Exact short-command payload witnesses; static model only, never launch RTL."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / 'verification/out/gap40-custom-analysis-20261004-01'
RTL = ['hardware/include/qbs_pkg.sv', 'hardware/src/ara_dispatcher.sv',
       *['hardware/src/vlsu/qbs/' + n + '.sv' for n in
         ('qbs_descriptor_decoder', 'qbs_engine', 'qbs_read_engine',
          'qbs_compute_engine', 'qbs_block_adapter', 'qbs_payload_buffer')]]
COMMANDS = [
    dict(id=0, weight='Q5_K', m=4, n=1, activation_layout='ROW_MAJOR', a_mod16=4,
         weight_row=7, k_block=1, contexts=[0, 1, 2, 3]),
    dict(id=1, weight='Q5_K', m=3, n=1, activation_layout='ROW_MAJOR', a_mod16=8,
         weight_row=8, k_block=2, contexts=[4, 5, 6]),
    dict(id=2, weight='Q2_K', m=2, n=8, activation_layout='ROW_MAJOR', a_mod16=12,
         weight_row=8, k_block=0, contexts=[0, 0]),
    dict(id=3, weight='Q5_K', m=5, n=1, activation_layout='M8', a_mod16=4,
         weight_row=9, k_block=3, contexts=[7, 8, 9, 10, 11]),
]
STREAM = re.compile(r'gen_write_merge\[(\d)\]\.gen_bank_plane\[(\d)\]\.'
                    r'gen_bank_row\[(\d)\]\.gen_byte_merge\[(\d+)\]\.byte_valid')
SIDE = re.compile(r'gen_side_row\[(\d)\]\.gen_weight_byte\[(\d+)\]\.enable')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_routes(model, command, bank):
    m, phase = command['m'], command['a_mod16']
    seq = []
    if command['activation_layout'] == 'ROW_MAJOR':
        if bank == 0:
            for context in range(m):
                seq.extend(model.beats(292, (phase + context * 292) % 16,
                    lambda b, c=context: (c, *model.aloc('Q8_K', b))))
    else:
        def mapper(b):
            if b < 32:
                context, native = divmod(b, 4)
            elif b < 2080:
                quant, context = divmod(b - 32, 8)
                native = 4 + quant
            else:
                x = b - 2080
                context = (x // 2) % 8
                native = 260 + (x // 16) * 2 + x % 2
            return ((context - bank * 4, *model.aloc('Q8_K', native))
                    if bank * 4 <= context < bank * 4 + 4 else None)
        seq = model.beats(8 * 292, phase, mapper)
    activation, _ = model.simulate(seq, True)
    seq = []
    size = model.PROFILES[command['weight']]
    for row in range(max(0, min(4, command['n'] - 4 * bank))):
        global_row = 4 * bank + row
        seq.extend(model.beats(size, global_row * size % 16,
            lambda b, r=row: (r, *model.wloc(command['weight'], b))))
    weight, side = model.simulate(seq, False)
    return activation | weight, side


def analyze():
    old_pins = read(HISTORY / 'payload-input-hashes.json')
    sources = [ROOT / path for path in RTL]
    for path in sources:
        if sha(path) != old_pins[str(path)]:
            raise ValueError('RTL differs from reviewed witness model: ' + str(path))
    build_pins_path = HISTORY.with_name('repaired-aligned-build-20260930-01') / 'build-source-pins.json'
    commit = ROOT / 'hardware/src/vlsu/qbs/qbs_commit.sv'
    if sha(commit) != read(build_pins_path)[str(commit)]:
        raise ValueError('commit RTL differs from the frozen instrumented build')
    sources += [commit, build_pins_path]
    model_path = HISTORY / 'payload_analysis.py'
    spec = importlib.util.spec_from_file_location('gap51_routing_model', model_path)
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    points = [dict(id=i, **p) for i, p in enumerate(p for p in
        read(HISTORY / 'payload-classification.json') if p['classification'].startswith('REACHABLE_'))]
    prior = {p['id'] for p in points if p['witness'].get('profile') == 'Q5_K'}
    remaining = {p['id'] for p in points} - prior
    commands, covered = [], set()
    for original in COMMANDS:
        c = dict(original, k_blocks=1, w_mod16=0, weight_layout='ROW_MAJOR',
                 activation='Q8_K', activation_access='DIRECT', vd=8)
        routes = [command_routes(model, c, bank) for bank in (0, 1)]
        hits = []
        for p in points:
            bank = int(re.search(r'i_block_adapter_bank(\d)', p['scope'])[1])
            expr = p['expressions'][0]['exprstr']
            match, side = STREAM.fullmatch(expr), SIDE.fullmatch(expr)
            if match and tuple(map(int, match.groups())) in routes[bank][0]:
                hits.append(p['id'])
            elif side and (1, *map(int, side.groups())) in routes[bank][1]:
                hits.append(p['id'])
        c['target_ids'] = sorted(set(hits) & remaining)
        c['new_target_ids'] = sorted(set(c['target_ids']) - covered)
        c['weight_bytes'] = c['n'] * model.PROFILES[c['weight']]
        c['activation_bytes'] = (8 if c['activation_layout'] == 'M8' else c['m']) * 292
        covered.update(c['target_ids'])
        commands.append(c)
    if len(points) != 52 or len(prior) != 16 or covered != remaining:
        raise ValueError('four commands do not cover precisely the remaining 36 points')
    if [len(c['new_target_ids']) for c in commands] != [12, 8, 12, 4]:
        raise ValueError('per-command routing prediction changed')
    sources += [HISTORY / name for name in ('payload-classification.json',
                'payload-routing-evidence.json', 'payload-input-hashes.json', 'payload_analysis.py')]
    sources += [Path(__file__).resolve(), ROOT / 'apps/common/qbs_abi.h']
    return dict(status='STATIC_ROUTING_MODEL_NOT_RTL_PASS', simulations_started=False,
        measured_gain=None, timeout_s=600, custom_commands=4, active_outputs=28,
        total_weight_bytes=sum(c['weight_bytes'] for c in commands),
        total_activation_bytes=sum(c['activation_bytes'] for c in commands),
        commands=commands, prior_gap49_target_ids=sorted(prior), remaining_target_ids=sorted(remaining),
        points=points, source_hashes={str(p): sha(p) for p in sorted(sources)},
        limits=['Remaining is relative to gap49 target assignment; this model does not audit its VDB.',
                'Continuous-input routing recurrence is not a cycle-accurate hit guarantee.',
                'Four-command lower bound applies to supplied single-K activation phase families.',
                'Q2_K M2 replays the single captured token twice; no second captured token claimed.',
                'M8 pads contexts5..7; physical routing is not numerical execution of padding.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = analyze()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('STATIC ONLY: four K1 commands, 28 outputs, 36 potential remaining points')


if __name__ == '__main__':
    main()
