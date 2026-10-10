#!/usr/bin/env python3
"""Generate signed partial sums and independently rounded SLDU expectations."""
import argparse
import random
from pathlib import Path
from gen_exact_reduction_oracle import decode_fixed, round_fixed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--count', type=int, default=1200)
    args = parser.parse_args()
    rng = random.Random(0x510020261007)
    edges = [0, 1, -1]
    for bit in [63, 64, 127, 128, 191, 192, 255, 256, 280]:
        for delta in [-1, 0, 1]:
            edges += [(1 << bit) + delta, -((1 << bit) + delta)]
    with args.output.open('w') as out:
        for case in range(args.count):
            fp16 = case % 4 == 0
            rm = (case // 4) % 5
            if fp16:
                values = [rng.randint(-(1 << 40), 1 << 40) << 125 for _ in range(4)]
            elif case % 3 == 0:
                values = [rng.choice(edges) for _ in range(4)]
            else:
                values = [rng.getrandbits(rng.choice([1, 64, 128, 192, 256, 281])) * rng.choice([-1, 1]) for _ in range(4)]
            if case % 7 == 0:
                values[1] = -values[0]
                values[3] = -values[2]
            if case % 11 == 0:
                values[0] = values[1] = values[2] = values[3] = 0
            seed = 0x3c00 if fp16 else 0x3f800000
            root = sum(values)
            assert -(1 << 287) <= root < (1 << 287)
            result, flags = round_fixed(root + decode_fixed(seed, fp16), rm, fp16, True, False, False)
            out.write(f'{int(fp16)} {rm} {seed:08x} {root % (1 << 288):072x} {result:08x} {flags:02x}\n')
            for value in values:
                # Include a whole sign-extension guard above significant data.
                significant = value if value >= 0 else ~value
                count = min(5, max(2, (significant.bit_length() + 63) // 64 + 1))
                if case % 5 == 0:
                    count = rng.randint(count, 5)  # legal dense-window variant
                out.write(f'{value % (1 << 288):072x} {count}\n')
    print(f'wrote {args.count} SLDU packet cases')


if __name__ == '__main__':
    main()
