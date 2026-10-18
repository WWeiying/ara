#!/usr/bin/env python3
"""Independent signed-integer exact-frame windows and FP32/FP16 expectations."""
import argparse
import itertools
import random
from pathlib import Path
from gen_exact_reduction_oracle import decode_fixed, round_fixed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--mode', choices=['legacy', 'compact', 'mixed'], default='mixed')
    p.add_argument('--seed-fold', action='store_true')
    p.add_argument('--seed-receive', type=int, choices=[0,1], default=1)
    args = p.parse_args()
    algebra_checks = 0
    for width in range(1, 4):
        base = 1 << width
        for values in itertools.product(range(-base, base), repeat=4):
            for carry in range(4):
                word_sum = sum(v % base for v in values) + carry
                upper = word_sum // base - sum(v < 0 for v in values)
                assert word_sum % base + upper * base == sum(values) + carry
                algebra_checks += 1
    if args.seed_fold:
        for width in range(1, 3):
            base = 1 << width
            for values in itertools.product(range(-base, base), repeat=5):
                for carry in range(5):
                    word_sum = sum(v % base for v in values) + carry
                    upper = word_sum // base - sum(v < 0 for v in values)
                    assert -5 <= upper <= 4
                    assert word_sum % base + upper * base == sum(values) + carry
                    algebra_checks += 1
    rng = random.Random(0x5a17288)
    directed = [
        [1 << 149, 1 << 150, 0, 0],
        [-(1 << 149), 1 << 150, 0, 0],
        [1 << 64, -(1 << 128), 1 << 192, -(1 << 256)],
        [0, 0, 0, 0],
        [-(1 << 64), -(1 << 128), -(1 << 192), -(1 << 256)],
        [1 << 149, -(1 << 149), 0, 0],
        [(1 << 260) + (1 << 128), -(1 << 260), 1 << 64, -1],
    ]
    cases = []
    # Both dense and omitted-low-zero encodings of every directed value.
    for fp16 in [0, 1]:
        for dense in [0, 1]:
            for values in directed:
                if fp16:
                    values = [(-1 if v < 0 else 1) * ((abs(v) >> 128) if abs(v).bit_length()>180 else abs(v)) for v in values]
                    values = [v // (1 << 125) * (1 << 125) for v in values]
                cases.append((fp16, dense, list(values)))
    for n in range(52):
        fp16 = n % 2
        values = []
        for lane in range(4):
            low = rng.choice([0, 64, 128, 192, 256])
            if fp16:
                low = rng.choice([125, 128, 144, 160])
            width = 10 if fp16 else max(1, min(24, 280 - low))
            value = rng.getrandbits(width) << low
            values.append(-value if rng.randrange(2) else value)
        cases.append((fp16, n % 5 == 0, values))
    cases = [(fmt, dense, vals, args.mode == 'compact') for fmt, dense, vals in cases]
    if args.mode != 'legacy':
        compact_directed = [
            [(1 << 64)-1]*4, [-(1 << 64)]*4,
            [1 << 63, -(1 << 63)-1, 1, -1],
            [-(1 << 64), 0, 0, 0],
            [1 << 127, -(1 << 127)-1, 1 << 64, 1],
            [1 << 191, -(1 << 191)-1, 1 << 128, -1],
            [1 << 255, -(1 << 255)-1, 1 << 192, 3],
            [1 << 270, -(1 << 270), 1 << 256, -1],
            [3, 7, -11, 19],
            [1 << 64, -(1 << 128), 1 << 192, -(1 << 256)],
            [1 << 149, -(1 << 149), 1 << 260, -(1 << 260)],
            [0, 0, 0, 0],
            [-(1 << 64), -(1 << 128), -(1 << 192), -(1 << 256)],
        ]
        for compact in [False, True]:
            for dense in [False, True]:
                cases.extend((0, dense, vals, compact) for vals in compact_directed)
                cases.extend((1, dense, vals, compact) for vals in [
                    [1 << 127, -(1 << 127)- (1 << 125), 1 << 128, -(1 << 128)],
                    [1 << 149, -(1 << 149), 1 << 150, 0]])
    overrides = {}
    if args.seed_fold:
        for fmt in [0, 1]:
            seeds = ([0x3c00,0xbc00,0,0x8000,0x7e00,0x7c01,0x7c00,0xfc00,1,0x7bff]
                     if fmt else [0x3f800000,0xbf800000,0,0x80000000,0x7fc00000,0x7f800001,0x7f800000,0xff800000,1,0x7f7fffff])
            windows = [
                ([1 << 149, 1 << 150, 0, 0], False),
                ([1 << (160 if fmt else 256), 0, 0, 0], False),
                ([1 << (125 if fmt else 64), 0, 0, 0], False),
                ([1 << 270, -(1 << 270), 1 << (125 if fmt else 0), -(1 << (125 if fmt else 0))], True),
                ([-(1 << 192)]*4, True),
                ([(1 << 192)-(1 << (125 if fmt else 0))]*4, True),
            ]
            for seed in seeds:
                for timing in range(3):  # ordinary, late-ready-at-header, delayed
                    for values, dense in windows:
                        overrides[len(cases)] = (seed, timing != 0, timing == 1)
                        cases.append((fmt, dense, values, True))
    lines = []
    for n, (fp16, dense, values, compact) in enumerate(cases):
        seed = (0x3c00 if fp16 else 0x3f800000) if n % 3 else 0
        late = int(n % 3 == 1 or n in (3, 17))
        header_ready = 0
        if n in overrides:
            seed, late, header_ready = overrides[n]
        rm = n % 6
        fracbits, expbits = (10, 5) if fp16 else (23, 8)
        frac = seed & ((1 << fracbits)-1)
        exponent = (seed >> fracbits) & ((1 << expbits)-1)
        sign = (seed >> (fracbits+expbits)) & 1
        special = exponent == (1 << expbits)-1
        nan = special and frac != 0
        snan = nan and not (frac & (1 << (fracbits-1)))
        seed_fixed = 0 if special else decode_fixed(seed, bool(fp16))
        total = sum(values) + seed_fixed
        nonzero = any(values) or (not special and seed_fixed != 0)
        assert abs(total) < (1 << 287), 'architectural root must not wrap'
        assert not fp16 or all(v % (1 << 125) == 0 for v in values)
        answer, flags = round_fixed(total, rm, bool(fp16), nonzero, not nonzero, False)
        # The shared integer oracle implements RNE..RMM. ROD preserves a
        # discarded nonzero tail by setting the retained significand odd.
        if rm == 5 and flags == 1:
            answer |= 1
        if special:
            answer = (0x7e00 if fp16 else 0x7fc00000) if nan else seed
            flags = int(snan) << 4
        metadata_special = (8 | (4 if snan else 0)) if nan else ((1 if sign else 2) if special else 0)
        metadata_nonzero = int(nonzero)
        metadata_poszero = int(any(v == 0 for v in values) or (not special and seed_fixed == 0 and not sign))
        metadata_negzero = int(not special and seed_fixed == 0 and sign)
        fields = [str(n), str(fp16), str(rm), str(int(late)), f'{seed:08x}',
                  f'{answer:08x}', f'{flags:02x}']
        starts, ends = [], []
        for value in values:
            bits = value & ((1 << 288) - 1)
            end = 5
            for count in range(1 if compact else 2, 6):
                signed_width = min(count * 64, 288)
                fits = (value >> signed_width) == (-1 if value < 0 else 0) if compact else -(1 << (signed_width - 1)) <= value < (1 << (signed_width - 1))
                if fits:
                    end = count
                    break
            skip = 0
            if not dense:
                skip = 5 if not value else min(4, ((bits & -bits).bit_length() - 1) // 64)
            starts.append(skip+1);ends.append(end)
            fields += [str(skip), str(end), f'{bits:072x}']
        if args.seed_fold:
            start, end = min(starts), max(ends)
            low_fits = seed_fixed % (1 << (64*(start-1))) == 0
            high_fits = (seed_fixed >> min(288,64*end)) == (-1 if seed_fixed < 0 else 0)
            folded = int((not late or header_ready or not args.seed_receive) and start <= end and low_fits and high_fits)
            fields += [f'{seed_fixed & ((1<<288)-1):072x}', str(folded), str(int(header_ready)),
                       f'{metadata_special:x}',str(metadata_nonzero),str(metadata_poszero),str(metadata_negzero)]
        lines.append(' '.join(fields))
    args.output.write_text('\n'.join(lines) + '\n')
    print(f'Generated {len(lines)} exact window cases mode={args.mode}; exhaustive upper-correction checks={algebra_checks}')


if __name__ == '__main__':
    main()
