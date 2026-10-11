#!/usr/bin/env python3
"""Independent scalar oracle for packed lane-local RCE inputs.

Integer expectations flatten all elements and reduce with Python arbitrary
precision, rather than replaying the DUT's lane-tree/horizontal-fold schedule.
FP extreme expectations compare exact binary encodings with explicit NaN/zero
semantics. Seeds, IEEE edges, all-inactive and VL=0 are intentionally frequent.
"""
import argparse
import functools
import operator
from pathlib import Path
import random

OPS = ['sum', 'and', 'or', 'xor', 'minu', 'min', 'maxu', 'max',
       'wsumu', 'wsum', 'fmin', 'fmax']


def fp_info(x, w):
    frac = {16: 10, 32: 23, 64: 52}[w]
    exp = {16: 5, 32: 8, 64: 11}[w]
    fraction = x & ((1 << frac) - 1)
    nan = ((x >> frac) & ((1 << exp) - 1)) == (1 << exp) - 1 and fraction != 0
    return nan, nan and not (fraction & (1 << (frac - 1)))


def fp_key(x, w):
    # Monotonic bit key for non-NaNs, including -0 < +0.
    return (~x & ((1 << w) - 1)) if x >> (w - 1) else x | (1 << w)


def reduce_values(op, w, values):
    mask = (1 << w) - 1
    if op.startswith('f'):
        info = [fp_info(x, w) for x in values]
        finite_or_inf = [x for x, (nan, _) in zip(values, info) if not nan]
        invalid = any(snan for _, snan in info)
        canonical = {16: 0x7e00, 32: 0x7fc00000, 64: 0x7ff8000000000000}[w]
        if not finite_or_inf:
            return canonical, int(invalid) << 4
        pick = min if op == 'fmin' else max
        return pick(finite_or_inf, key=lambda x: fp_key(x, w)), int(invalid) << 4
    if op in ['sum', 'wsumu', 'wsum']:
        return sum(values) & mask, 0
    if op in ['and', 'or', 'xor']:
        return functools.reduce({'and': operator.and_, 'or': operator.or_,
                                 'xor': operator.xor}[op], values), 0
    signed = op in ['min', 'max']
    vals = [x - (1 << w) if signed and x >> (w - 1) else x for x in values]
    return ((min(vals) if op.startswith('min') else max(vals)) & mask), 0


def neutral(op, w):
    if op.startswith('f'):
        return {16: 0x7e00, 32: 0x7fc00000, 64: 0x7ff8000000000000}[w]
    if op in ['and', 'minu']:
        return (1 << w) - 1
    if op == 'min':
        return (1 << (w - 1)) - 1
    if op == 'max':
        return 1 << (w - 1)
    return 0


def generate(path, count, seed=0x5243452026):
    rng = random.Random(seed)
    configurations = [(op, w) for op in OPS for w in [8, 16, 32, 64]
                      if not (op.startswith('f') and w == 8)
                      and not (op.startswith('w') and w == 8)]
    with Path(path).open('w') as out:
        for n in range(count):
            op, w = configurations[n % len(configurations)]
            mask = (1 << w) - 1
            seed_mode = (n // len(configurations)) % 3
            vl_zero = n % 31 == 0
            active = 0 if n % 7 == 0 else rng.randint(1, 15)
            edges = [0, 1, mask, mask >> 1, 1 << (w - 1)]
            if op.startswith('f'):
                canonical = neutral(op, w)
                fraction = {16: 10, 32: 23, 64: 52}[w]
                infinity = canonical & ~(1 << (fraction - 1))
                edges = [0, 1 << (w - 1), infinity, infinity | (1 << (w - 1)),
                         canonical, canonical | 7, infinity | 1, 1,
                         (1 << fraction) - 1, 1 << fraction,
                         {16: 0x3c00, 32: 0x3f800000, 64: 0x3ff0000000000000}[w]]
            def value():
                return rng.choice(edges) if n % 3 else rng.getrandbits(w)
            scalar_seed = value()
            original_values = []
            words, flags = [], []
            for lane in range(4):
                vals = [value() if active & (1 << lane) else neutral(op, w)
                        for _ in range(64 // w)]
                if active & (1 << lane):
                    original_values.extend(vals)
                local_flags = 0
                if seed_mode == 0 and lane == 0:
                    # Existing lane seed-insertion mode. NV may already have
                    # occurred locally; empty-source override must suppress it.
                    vals[0], local_flags = reduce_values(op, w, [vals[0], scalar_seed])
                words.append(sum(x << (i * w) for i, x in enumerate(vals)))
                flags.append(local_flags)
            if vl_zero:
                expected, fflags = 0, 0
            elif not active:
                expected, fflags = scalar_seed, 0
            else:
                expected, fflags = reduce_values(op, w, original_values + [scalar_seed])
            out.write(f'{OPS.index(op)} {w.bit_length()-4} {seed_mode} {int(vl_zero)} '
                      f'{scalar_seed:016x} {active:x} {expected:016x} {fflags:02x}\n')
            for word, flag in zip(words, flags):
                out.write(f'{word:016x} {flag:02x}\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=2640)
    parser.add_argument('--seed', type=lambda s: int(s, 0), default=0x5243452026)
    args = parser.parse_args()
    generate(args.output, args.count, args.seed)
    print(f'wrote {args.count} RCE word cases')
