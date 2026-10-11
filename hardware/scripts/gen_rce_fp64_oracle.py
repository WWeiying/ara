#!/usr/bin/env python3
"""Independent FP64 add model using exact Python integers in units of 2**-1074.

The completion contract folds lane partials in lane-number order. Inactive
nonseed subtrees are copied past. Each active node rounds independently using
the command's dynamic rounding mode. This is not an exact-sum backend.
"""
import argparse
from pathlib import Path
import random

SIGN = 1 << 63
INF = 0x7ff0000000000000
QNAN = 0x7ff8000000000000
FRAC = (1 << 52) - 1


def add(a, b, rm):
    def classify(x):
        exp, frac = (x >> 52) & 2047, x & FRAC
        return exp, frac, exp == 2047 and frac != 0
    ea, fa, na = classify(a)
    eb, fb, nb = classify(b)
    if na or nb:
        return QNAN, 16 if ((na and not fa & (1 << 51)) or
                            (nb and not fb & (1 << 51))) else 0
    if ea == 2047 or eb == 2047:
        if ea == eb == 2047 and (a ^ b) & SIGN:
            return QNAN, 16
        return a if ea == 2047 else b, 0
    def fixed(x, e, f):
        value = (f | ((1 << 52) if e else 0)) << max(e - 1, 0)
        return -value if x & SIGN else value
    exact = fixed(a, ea, fa) + fixed(b, eb, fb)
    if exact == 0:
        same_signed_zeros = (a & ~SIGN) == (b & ~SIGN) == 0 and a == b
        return (a if same_signed_zeros else SIGN if rm == 2 else 0), 0
    sign = SIGN if exact < 0 else 0
    magnitude = abs(exact)
    shift = max(0, magnitude.bit_length() - 53)
    quotient, remainder = divmod(magnitude, 1 << shift)
    half = (1 << shift) // 2
    increment = False
    if remainder:
        if rm == 0: increment = remainder > half or (remainder == half and quotient & 1)
        elif rm == 2: increment = bool(sign)
        elif rm == 3: increment = not sign
        elif rm == 4: increment = remainder >= half
    quotient += int(increment)
    if quotient >= 1 << 53:
        quotient >>= 1
        shift += 1
    exponent = shift + 1 if quotient >= 1 << 52 else 0
    if exponent >= 2047:
        infinity = rm in (0, 4) or (rm == 2 and sign) or (rm == 3 and not sign)
        return sign | (INF if infinity else INF - 1), 5
    return sign | (exponent << 52) | (quotient & FRAC), int(bool(remainder))


def generate(path, count, seed=0x5243456432):
    rng = random.Random(seed)
    edges = [0, SIGN, 1, SIGN | 1, FRAC, FRAC+1, INF-1, SIGN | (INF-1),
             INF, SIGN | INF, QNAN, INF | 1, SIGN | (INF | 1),
             0x3ff0000000000000, 0xbff0000000000000, 0x3ca0000000000000]
    with Path(path).open('w') as out:
        for n in range(count):
            rm = n % 5
            mode = (n // 5) % 3
            active = 0 if n % 17 == 0 else rng.randrange(1, 16)
            zero_vl = n % 43 == 0
            value = lambda: rng.choice(edges) if n % 3 else rng.getrandbits(64)
            seed = value()
            words = [value() if active & (1 << lane) else (0 if rm == 2 else SIGN)
                     for lane in range(4)]
            flags = [0] * 4
            if mode == 0:
                if active & 1: words[0], flags[0] = add(seed, words[0], rm)
                else: words[0] = seed
            total = words[0]
            status = flags[0]
            for lane in range(1, 4):
                if active & (1 << lane):
                    total, f = add(total, words[lane], rm)
                    status |= f
            if mode != 0:
                total, f = add(total, seed, rm)
                status |= f
            if not active: total, status = seed, 0
            if zero_vl: total, status = 0, 0
            # Low byte is the opcode index; high byte supplies FRM to the common TB.
            op = (12 + (n % 2)) | (rm << 8)
            out.write(f'{op} 3 {mode} {int(zero_vl)} {seed:016x} {active:x} '
                      f'{total:016x} {status:02x}\n')
            for word, f in zip(words, flags): out.write(f'{word:016x} {f:02x}\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--count', type=int, default=2000)
    p.add_argument('--seed', type=lambda s: int(s, 0), default=0x5243456432)
    a = p.parse_args()
    generate(a.output, a.count, a.seed)
