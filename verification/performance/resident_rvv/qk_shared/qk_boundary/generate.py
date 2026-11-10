#!/usr/bin/env python3
"""Bit-pattern inputs and independent ordered Spike SoftFloat QK results."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
from cases import SCHEMA, control, destination, scenarios

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DATA = OUT / 'e2e_qwen3_f16_native_data_20261106_02'
REFERENCE = ROOT / 'verification/performance/resident_rvv/ordered_reference.py'
LIB = Path('/home/wangwy/software/toolchains/spike/lib/libsoftfloat.so')
ANCHORS = {
    DATA / 'result.json': '0fb5797dfed0d5d6bfaaf1e7b611f110b9b0a625fa1b67977ba86ce7a9e3581a',
    DATA / 'decode_query_f16.bin': '24bdf29c0111f117fdb3ec460de88b96740e3a26b81e456e4d5be0d7ea4c4b99',
    DATA / 'decode_key.bin': '5d14e468e7788e589bccd0b504f1d32d8b9401a020ac0089ef9debccb4d6695f',
    REFERENCE: 'd22b94d1f28fcb6df10c3cf8af957dcb584b6f7a85b458666287d0b46e2d9e4e',
    LIB: 'dd2349915d26aacb040f24e4d576c8907ad42074797762a7d54b0cc028d59a77',
}


def need(ok, text):
    if not ok:
        raise ValueError(text)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(pins):
    for p, expected in pins.items():
        need(sha(p) == expected, 'Input drift: ' + str(p))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raw16(path):
    raw = Path(path).read_bytes()
    return list(struct.unpack('<' + 'H' * (len(raw) // 2), raw))


def oracle(ref, q, k, d, h, t, base, rm):
    r = ref.qk([q[(base + head) * 128:(base + head) * 128 + d] for head in range(h)],
               [k[token * 128:token * 128 + d] for token in range(t)], rm)
    return dict(expected=sum(r['output'], []), qk_flags=r['fflags'])


def construct(ref, raw_q, raw_k):
    need(len(raw_q) == 256 and len(raw_k) >= 64 * 128, 'Wrong captured Qwen3 shape')
    rows = []
    for spec in scenarios():
        s = dict(spec)
        # Deliberate model-derived, distinguishable rows, not an eight-head capture.
        q = [raw_q[(r % 2) * 128 + (d + 7 * r) % 128] for r in range(8) for d in range(128)]
        k = raw_k[:64 * 128]
        kind, b, h, d, t = (s[x] for x in ('kind', 'query_base', 'heads', 'dimension', 'tokens'))
        if kind in ('invalid', 'qnan', 'snan', 'poison_subnormal', 'rounding'):
            q, k = [0x3c00] * 1024, [0x3c00] * (64 * 128)
            if kind == 'invalid':
                q[b * 128], k[0] = 0, 0x7c00
            elif kind == 'qnan':
                q[b * 128], q[(b + 1) * 128] = 0x7e01, 0x7c00
            elif kind == 'snan':
                q[(b + 1) * 128 + 1] = 0xfc01
            elif kind == 'poison_subnormal':
                q, k = [0x7c01] * 1024, [0x7c01] * (64 * 128)
                q[b * 128:b * 128 + d] = [1 if x % 2 else 0x8001 for x in range(d)]
                for token in range(t):
                    k[token * 128:token * 128 + d] = [1] * d
            else:
                for head in range(h):
                    q[(b + head) * 128:(b + head) * 128 + d] = [0x7bff, 0x3c00, 0xfbff] + [0] * (d - 3)
                for token in range(t):
                    k[token * 128:token * 128 + d] = [0x7bff, 0x3c00, 0x7bff] + [0x3c00] * (d - 3)
        s.update(query=q, key=k)
        s.update(oracle(ref, q, k, d, h, t, b, s['rm']))
        s['expected_fcsr'] = (s['rm'] << 5) | s['initial_flags'] | s['qk_flags']
        if s['rejection']:
            gd, gt = s['context_dimension'], s['context_tokens']
            gb = 5 if kind == 'query_bounds' else b
            recovery = dict(dimension=gd, heads=h, tokens=gt, query_base=gb,
                            control=control(gd, h, gt, gb), initial_flags=s['initial_flags'], rm=s['rm'])
            recovery.update(oracle(ref, q, k, gd, h, gt, gb, s['rm']))
            recovery['expected_fcsr'] = (s['rm'] << 5) | s['initial_flags'] | recovery['qk_flags']
            s['recovery'] = recovery
        rows.append(s)
    by_kind = {s['kind']: s for s in rows}
    need(by_kind['invalid']['qk_flags'] & 16 and by_kind['snan']['qk_flags'] & 16 and
         by_kind['qnan']['qk_flags'] == 0 and by_kind['poison_subnormal']['qk_flags'] == 0 and
         by_kind['rounding']['qk_flags'] & 1, 'Required independent flag coverage missing')
    return rows


def header(payload):
    fields = ('id dimension heads tokens query_base rm initial_flags control bad_control mode bad_mode '
              'context_dimension context_tokens context_queries qk_flags expected_fcsr')
    lines = ['#include <stdint.h>', '#include "akv/akv_abi.h"', '#define QK_CASES 23',
             '#define QK_DATA_SHA256 "' + payload['data_identity_sha256'] + '"',
             'typedef struct { uint64_t ' + ','.join(fields.split()) + ';',
             'uint64_t rejection, kind, recovery_dimension, recovery_tokens, recovery_control, recovery_flags;',
             'const uint16_t *query, *key;', 'const uint32_t *expected, *recovery_expected;', '} qk_case_t;']
    kinds = list(dict.fromkeys(s['kind'] for s in payload['cases']))
    lines += ['#define KIND_' + kind.upper() + ' ' + str(i) for i, kind in enumerate(kinds)]
    arrays, ptr = {}, {}
    for s in payload['cases']:
        for key in ('query', 'key', 'expected', 'recovery_expected'):
            width = 16 if key in ('query', 'key') else 32
            data = s['recovery']['expected'] if key == 'recovery_expected' and s['rejection'] else s.get(key, s['expected'])
            identity = (width, tuple(data))
            if identity not in arrays:
                name = 'data_' + str(len(arrays))
                arrays[identity] = name
                lines.append(f'static const uint{width}_t {name}[] __attribute__((aligned(64))) = {{' +
                             ','.join(f'0x{x:0{width // 4}x}' for x in data) + '};')
            ptr[s['id'], key] = arrays[identity]
    lines += ['static const uint16_t qk_values[64*128] __attribute__((aligned(64))) = {[0 ... 64*128-1]=0x3c00};',
              'static const uint32_t qk_destination[384] __attribute__((aligned(64))) = {' +
              ','.join(f'0x{x:08x}' for x in destination()) + '};', 'static const qk_case_t qk_cases[] = {']
    for s in payload['cases']:
        rec = s.get('recovery', s)
        values = [s[f] for f in fields.split()] + [int(bool(s['rejection'])), kinds.index(s['kind']),
                  rec['dimension'], rec['tokens'], rec['control'], rec['qk_flags']]
        lines.append('{' + ','.join(map(str, values)) + ',' +
                     ','.join(ptr[s['id'], key] for key in ('query', 'key', 'expected', 'recovery_expected')) + '},')
    return '\n'.join(lines + ['};', ''])


def generate(output):
    verify(ANCHORS)
    ref = load(REFERENCE, 'qk_boundary_independent_reference').OrderedReference(LIB)
    identity = ref.identity()
    rows = construct(ref, raw16(DATA / 'decode_query_f16.bin'), raw16(DATA / 'decode_key.bin'))
    pins = {str(p): v for p, v in ANCHORS.items()} | identity
    pins.update({str(HERE / n): sha(HERE / n) for n in ('cases.py', 'generate.py')})
    payload = dict(schema=SCHEMA, cases=rows, destination_pattern=destination(), source_pins=pins,
                   provenance='Qwen3 captured two Q rows -> distinct dimension rotations; first 64 K rows. '
                              'Synthetic IEEE patches explicitly identified by kind. Not an eight-head model capture.',
                   numerical_only=True, hardware_acceptance=False)
    payload['data_identity_sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    verify(pins)
    output = Path(output)
    output.mkdir(exist_ok=False)
    (output / 'vectors.json').write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    (output / 'qk_data.h').write_text(header(payload))
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    print(json.dumps(dict(cases=len(generate(p.parse_args().output)['cases']), execution='NOT_RUN')))
