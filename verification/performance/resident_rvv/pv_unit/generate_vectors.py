#!/usr/bin/env python3
"""Bit-exact resident-PV stimuli; arithmetic comes only from Spike SoftFloat.

Text format: header, then case headers, seeds, packets, per-FMA expectations,
and commits. Each record count is explicit and checked by the testbench.
Modes: 0 normal, 1 invalid command, 2 bad packet, 3 reset, 4 parent abort.
"""
import argparse
import importlib.util
import itertools
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent / "ordered_reference.py"
ELEMENTS = (1, 2, 3, 4, 8, 16, 24, 31, 32)
TOKENS = (1, 2, 9, 64)
MAGIC = 0x50565531
SPECIAL = (0, 0x8000, 1, 0x8001, 0x3FF, 0x400, 0x3BFF, 0x3C00,
           0x3C01, 0xBC00, 0x7BFF, 0xFBFF, 0x7C00, 0xFC00, 0x7E00, 0x7C01)


def reference(library=None):
    spec = importlib.util.spec_from_file_location("pv_ordered_reference", REFERENCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.OrderedReference() if library is None else module.OrderedReference(library)


def pack(values, pad=0x7C01):
    if not 1 <= len(values) <= 4:
        raise ValueError("Expected one to four FP16 elements")
    return sum(v << (16 * i) for i, v in enumerate(list(values) + [pad] * (4-len(values))))


def prepared_case(ref, name, seed, coefficient, values, rm, prepared_flags=0):
    heads, elements, tokens = len(seed), len(seed[0]), len(values)
    if (heads not in (1, 2) or not 1 <= elements <= 32 or not 1 <= tokens <= 64
            or rm not in range(5) or not 0 <= prepared_flags <= 31
            or len(coefficient) != heads
            or any(len(row) != elements for row in seed + values)
            or any(len(row) != tokens for row in coefficient)
            or any(not isinstance(x, int) or not 0 <= x <= 65535
                   for row in seed + coefficient + values for x in row)):
        raise ValueError("Invalid prepared PV shape or bit pattern")
    words = (elements + 3)//4
    accum = [row[:] for row in seed]
    case = dict(name=name, elements=elements, heads=heads, tokens=tokens, rm=rm,
                mode=0, reset_phase=0, bad_at=-1, prepared_flags=prepared_flags,
                fma_flags=0, seeds=[], packets=[], ops=[], commits=[])
    for h in range(heads):
        for w in range(words):
            case['seeds'].append(dict(slot=h*8+w, data=pack(seed[h][w*4:w*4+4])))
    for t in range(tokens):
        case['packets'].append(dict(kind=0, data=coefficient[0][t] |
                                   ((coefficient[1][t] if heads == 2 else 0x7C01) << 16)))
        for w in range(words):
            chunk = values[t][w*4:w*4+4]
            case['packets'].append(dict(kind=1, data=pack(chunk)))
            for h in range(heads):
                before = accum[h][w*4:w*4+4]
                result, flags = [], 0
                for i, v in enumerate(chunk):
                    r, f = ref.sf.evaluate('fma', 16, 16, rm, coefficient[h][t], v, before[i])
                    result.append(r)
                    flags |= f
                accum[h][w*4:w*4+len(chunk)] = result
                case['ops'].append(dict(token=t, slot=h*8+w, mask=(1 << len(chunk))-1,
                    a=pack([coefficient[h][t]]*4), b=pack(chunk), c=pack(before),
                    result=pack(result), flags=flags))
                case['fma_flags'] |= flags
    for h in range(heads):
        for w in range(words):
            chunk = accum[h][w*4:w*4+4]
            case['commits'].append(dict(slot=h*8+w, be=(1 << (2*len(chunk)))-1,
                                        data=pack(chunk)))
    case['output'] = accum
    case['complete_flags'] = prepared_flags | case['fma_flags']
    return case


def complete_case(ref, name, probability, scale, seed, values, rm):
    whole = ref.pv(probability, scale, seed, values, rm)
    case = prepared_case(ref, name, whole['prepared_seed'], whole['coefficient'],
                         values, rm, whole['prepared_fflags'])
    if case['output'] != whole['output'] or case['complete_flags'] != whole['fflags']:
        raise ValueError("Prepared/FMA split disagrees with ordered_reference.pv")
    case['preparation_crosschecked'] = True
    return case


def cases(ref, seed=0x505631, random_cases=32):
    rng = random.Random(seed)
    rows = []
    # Both deterministic directed and random matrices cover the full cross product.
    for random_data, n, heads, tokens, rm in itertools.product(
            (False, True), ELEMENTS, (1, 2), TOKENS, range(5)):
        def half(i):
            if random_data:
                # Finite inputs keep long recurrences informative instead of NaN-only.
                return rng.randrange(0x7400) | (rng.randrange(2) << 15)
            return (0x3C00, 0xBC00, 1, 0x3BFF, 0x400, 0x8000)[i % 6]
        initial = [[half(h*7+i) for i in range(n)] for h in range(heads)]
        values = [[half(t*3+i+2) for i in range(n)] for t in range(tokens)]
        probability = [[rng.choice((0x3EAAAAAB, 0x3F000000, 0x3F800001, 0x33800000))
                        if random_data else (0x3F000000, 0xBF000000)[(h+t) % 2]
                        for t in range(tokens)] for h in range(heads)]
        rows.append(complete_case(ref, f"matrix_{int(random_data)}_{n}_{heads}_{tokens}_{rm}",
            probability, [0x3F800000]*heads, initial, values, rm))
    triples = (
        (0, 0x7C00, 0), (0x7C00, 0x3C00, 0xFC00),
        (0x7C01, 0x3C00, 0), (0x3C00, 0x7C01, 0), (0x3C00, 0x3C00, 0x7C01),
        (0x7E00, 0x3C00, 0), (0x7BFF, 0x4000, 0),
        (1, 0x3800, 0), (0x3C01, 0x3C01, 0xBC00),
        (0x8000, 0x3C00, 0x8000), (0x3C00, 0x3C00, 0xBC00),
        (0x300, 0x3BFF, 0x100),
    )
    for rm, (p, v, s) in itertools.product(range(5), triples):
        rows.append(prepared_case(ref, f"special_{rm}_{p:x}_{v:x}_{s:x}",
                    [[s]*3, [s]*3], [[p], [p]], [[v]*3], rm))
    # sNaN poison in inactive lanes must not raise NV, even for a one-element word.
    for n, heads, rm in itertools.product((1, 3, 31), (1, 2), range(5)):
        rows.append(prepared_case(ref, f"tail_{n}_{heads}_{rm}",
                    [[0]*n for _ in range(heads)], [[0x3C00] for _ in range(heads)],
                    [[0x3C00]*n], rm))
    # Preparation can raise NV while every controller FMA raises no flags.
    rows.append(complete_case(ref, 'preparation_only_NV', [[0x7F800001]], [0x3F800000],
                              [[0]], [[0x3C00]], 0))
    for i in range(random_cases):
        n, heads, tokens, rm = (rng.choice(ELEMENTS), rng.choice((1, 2)),
                               rng.choice(TOKENS), rng.randrange(5))
        def bits():
            return rng.choice(SPECIAL) if rng.randrange(2) else rng.randrange(65536)
        rows.append(prepared_case(ref, f"random_special_{i}",
            [[bits() for _ in range(n)] for _ in range(heads)],
            [[bits() for _ in range(tokens)] for _ in range(heads)],
            [[bits() for _ in range(n)] for _ in range(tokens)], rm))
    for n, tokens, rm in ((0, 1, 0), (33, 1, 0), (63, 1, 0), (4, 0, 0),
                           (4, 65, 0), (4, 127, 0), (4, 1, 5), (4, 1, 6), (4, 1, 7)):
        for heads in (1, 2):
            rows.append(dict(name=f"invalid_{n}_{tokens}_{rm}_{heads}", elements=n,
                heads=heads, tokens=tokens, rm=rm, mode=1, reset_phase=0, bad_at=-1,
                prepared_flags=0, fma_flags=0, complete_flags=0,
                seeds=[], packets=[], ops=[], commits=[]))
    for heads, bad_at in itertools.product((1, 2), (0, 1, 2, 9, 10)):
        row = prepared_case(ref, f"bad_packet_{heads}_{bad_at}", [[0]*32]*heads,
                            [[0x3C01]*2]*heads, [[0x3C01]*32]*2, 0)
        row.update(mode=2, bad_at=bad_at)
        row['packets'] = row['packets'][:bad_at+1]
        row['packets'][-1]['kind'] ^= 1
        rows.append(row)
    for phase in range(1, 6):
        rows.append(prepared_case(ref, f"reset_phase_{phase}", [[0]*32]*2,
                                 [[0x3C01]*2]*2, [[0x3C01]*32]*2, phase-1))
        rows[-1].update(mode=3, reset_phase=phase)
        # No reset between the interruption and this recovery command.
        rows.append(prepared_case(ref, f"reset_recovery_{phase}", [[0xBC00]],
                                 [[0x3C00]*2], [[0x4000]]*2, 0))
    for phase in (1, 3, 4):
        row = prepared_case(ref, f"abort_phase_{phase}", [[0]*32]*2,
                            [[0x3C01]*2]*2, [[0x3C01]*32]*2, 0)
        row.update(mode=4, reset_phase=phase)
        rows.append(row)
        rows.append(prepared_case(ref, f"abort_recovery_{phase}", [[0xBC00]],
                                 [[0x3C00]*2], [[0x4000]]*2, 0))
    for i, row in enumerate(rows):
        row['id'] = i
    return rows


def real_cases(ref, path):
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload.get('artifacts'), dict) or not payload.get('cases'):
        raise ValueError('Real corpus requires cases and artifact pins')
    result = []
    for raw in payload['cases']:
        row = prepared_case(ref, raw['name'], raw['seed'], raw['coefficient'],
                            raw['values'], raw['rm'])
        if any(row[k] != raw[k] for k in ('heads', 'elements', 'tokens')):
            raise ValueError('Real shape metadata disagrees with data')
        if row['output'] != raw['expected'] or row['fma_flags'] != raw['flags']:
            raise ValueError('Real recorded result/flags disagree with SoftFloat: '+raw['name'])
        row['real'] = True
        result.append(row)
    if len({r['name'] for r in result}) != len(result):
        raise ValueError('Duplicate real case names')
    return result


def write_vectors(path, rows):
    with Path(path).open('x') as f:
        f.write(f"{MAGIC:x} {len(rows)}\n")
        for r in rows:
            fields = ('id', 'elements', 'heads', 'tokens', 'rm', 'mode', 'reset_phase', 'bad_at')
            counts = [len(r[k]) for k in ('seeds', 'packets', 'ops', 'commits')]
            f.write(' '.join(str(r[k]) for k in fields) + ' ' + ' '.join(map(str, counts)) +
                    f" {r['fma_flags']:x} {r['prepared_flags']:x}\n")
            for s in r['seeds']:
                f.write(f"{s['slot']:x} {s['data']:016x}\n")
            for s in r['packets']:
                f.write(f"{s['kind']} {s['data']:016x}\n")
            for op in r['ops']:
                f.write(f"{op['token']} {op['slot']:x} {op['mask']:x} " +
                        ' '.join(f"{op[k]:016x}" for k in ('a', 'b', 'c', 'result')) +
                        f" {op['flags']:x}\n")
            for s in r['commits']:
                f.write(f"{s['slot']:x} {s['be']:x} {s['data']:016x}\n")


def summary(rows):
    return dict(cases=len(rows), modes={str(m): sum(r['mode'] == m for r in rows) for m in range(5)},
        real_cases=sum(r.get('real', False) for r in rows),
        normal_fmas=sum(len(r['ops']) for r in rows if r['mode'] == 0),
        preparation_crosschecked=sum(r.get('preparation_crosschecked', False) for r in rows),
        cases_by_id=[{k: r[k] for k in ('id', 'name', 'mode', 'elements', 'heads', 'tokens',
                                       'rm', 'fma_flags', 'prepared_flags', 'complete_flags')}
                     for r in rows])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--library', type=Path)
    p.add_argument('--seed', type=lambda s: int(s, 0), default=0x505631)
    p.add_argument('--random-cases', type=int, default=32)
    p.add_argument('--real-json', type=Path)
    a = p.parse_args()
    if a.random_cases < 0:
        p.error('random-cases must be nonnegative')
    a.output.mkdir(parents=True, exist_ok=False)
    ref = reference(a.library)
    before = ref.identity()
    rows = cases(ref, a.seed, a.random_cases)
    if a.real_json:
        rows += real_cases(ref, a.real_json)
        for i, row in enumerate(rows):
            row['id'] = i
    if ref.identity() != before:
        raise ValueError('Oracle changed during generation')
    write_vectors(a.output/'vectors.txt', rows)
    with (a.output/'vectors.json').open('x') as f:
        json.dump(dict(summary(rows), oracle_pins=before, random_seed=a.seed), f, indent=2)
        f.write('\n')
    print(f"PV_VECTORS cases={len(rows)}")


if __name__ == '__main__':
    main()
