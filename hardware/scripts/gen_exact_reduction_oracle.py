#!/usr/bin/env python3
"""Generate independent exact-reduction reference vectors.

The model deliberately uses Python integers rather than host floating point.
Every finite binary16/binary32 operand is decoded into the RTL accumulator's
2^-149 coordinate system, summed without loss, and rounded once according to
the selected RISC-V rounding mode.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path


VECTOR_WIDTH = 141


def finite_value(rng: random.Random, fp16: bool) -> int:
    """Return arbitrary finite bits, with extra coverage at exponent edges."""
    frac_bits = 10 if fp16 else 23
    exp_bits = 5 if fp16 else 8
    sign_shift = frac_bits + exp_bits
    max_finite_exp = (1 << exp_bits) - 2
    edge_exponents = [0, 0, 1, 1, max_finite_exp - 1, max_finite_exp]
    exponent = (
        rng.choice(edge_exponents)
        if rng.randrange(3) == 0
        else rng.randrange(max_finite_exp + 1)
    )
    fraction = rng.getrandbits(frac_bits)
    sign = rng.getrandbits(1)
    return (sign << sign_shift) | (exponent << frac_bits) | fraction


def decode_fixed(bits: int, fp16: bool) -> int:
    frac_bits = 10 if fp16 else 23
    exp_bits = 5 if fp16 else 8
    sign_shift = frac_bits + exp_bits
    fraction = bits & ((1 << frac_bits) - 1)
    exponent = (bits >> frac_bits) & ((1 << exp_bits) - 1)
    sign = (bits >> sign_shift) & 1
    if exponent == 0:
        magnitude = fraction << (125 if fp16 else 0)
    elif fp16:
        magnitude = ((1 << frac_bits) | fraction) << (exponent + 124)
    else:
        magnitude = ((1 << frac_bits) | fraction) << (exponent - 1)
    return -magnitude if sign else magnitude


def is_zero(bits: int, fp16: bool) -> bool:
    sign_shift = 15 if fp16 else 31
    return (bits & ((1 << sign_shift) - 1)) == 0


def sign_bit(bits: int, fp16: bool) -> int:
    return (bits >> (15 if fp16 else 31)) & 1


def overflow_result(sign: int, rm: int, fp16: bool) -> int:
    frac_bits = 10 if fp16 else 23
    exp_bits = 5 if fp16 else 8
    max_exp = (1 << exp_bits) - 1
    if rm in (1, 5):
        to_inf = False
    elif rm == 2:
        to_inf = bool(sign)
    elif rm == 3:
        to_inf = not sign
    else:
        to_inf = True
    exponent = max_exp if to_inf else max_exp - 1
    fraction = 0 if to_inf else (1 << frac_bits) - 1
    return (sign << (frac_bits + exp_bits)) | (exponent << frac_bits) | fraction


def round_fixed(
    exact: int,
    rm: int,
    fp16: bool,
    finite_nonzero_seen: bool,
    pos_zero_seen: bool,
    neg_zero_seen: bool,
) -> tuple[int, int]:
    frac_bits = 10 if fp16 else 23
    exp_bits = 5 if fp16 else 8
    bias = 15 if fp16 else 127
    quantum_bit = 125 if fp16 else 0
    subnormal_msb_limit = quantum_bit + frac_bits
    max_exponent = bias
    sign = int(exact < 0)
    magnitude = abs(exact)

    if magnitude == 0:
        if not finite_nonzero_seen and neg_zero_seen and not pos_zero_seen:
            zero_sign = 1
        elif not finite_nonzero_seen and pos_zero_seen and not neg_zero_seen:
            zero_sign = 0
        else:
            zero_sign = int(rm == 2)
        return zero_sign << (frac_bits + exp_bits), 0

    msb = magnitude.bit_length() - 1
    if msb < subnormal_msb_limit:
        fraction = magnitude >> quantum_bit
        return (sign << (frac_bits + exp_bits)) | fraction, 0

    exponent = msb - 149
    shift = msb - frac_bits
    if exponent > max_exponent:
        return overflow_result(sign, rm, fp16), 0b00101

    significand = magnitude >> shift
    discarded = magnitude & ((1 << shift) - 1) if shift else 0
    guard = (magnitude >> (shift - 1)) & 1 if shift else 0
    sticky = bool(discarded & ((1 << (shift - 1)) - 1)) if shift > 1 else False
    inexact = bool(guard or sticky)

    if rm == 0:
        increment = bool(guard and (sticky or (significand & 1)))
    elif rm == 1:
        increment = False
    elif rm == 2:
        increment = bool(sign and inexact)
    elif rm == 3:
        increment = bool((not sign) and inexact)
    elif rm == 4:
        increment = bool(guard)
    else:
        increment = False
    significand += int(increment)

    if significand >> (frac_bits + 1):
        significand >>= 1
        exponent += 1
    if exponent > max_exponent:
        return overflow_result(sign, rm, fp16), 0b00101

    encoded_exp = exponent + bias
    result = (
        (sign << (frac_bits + exp_bits))
        | (encoded_exp << frac_bits)
        | (significand & ((1 << frac_bits) - 1))
    )
    return result, int(inexact)


def make_vector(rng: random.Random, fp16: bool, rm: int) -> int:
    count = 4 if fp16 else 2
    values = [finite_value(rng, fp16) for _ in range(count)]
    active = rng.randrange(1 << count)
    seed = finite_value(rng, fp16)

    exact = decode_fixed(seed, fp16)
    finite_nonzero_seen = not is_zero(seed, fp16)
    pos_zero_seen = is_zero(seed, fp16) and not sign_bit(seed, fp16)
    neg_zero_seen = is_zero(seed, fp16) and bool(sign_bit(seed, fp16))
    for index, value in enumerate(values):
        if active & (1 << index):
            exact += decode_fixed(value, fp16)
            finite_nonzero_seen |= not is_zero(value, fp16)
            pos_zero_seen |= is_zero(value, fp16) and not sign_bit(value, fp16)
            neg_zero_seen |= is_zero(value, fp16) and bool(sign_bit(value, fp16))

    if active == 0:
        expected, status = seed, 0
    else:
        expected, status = round_fixed(
            exact,
            rm,
            fp16,
            finite_nonzero_seen,
            pos_zero_seen,
            neg_zero_seen,
        )

    if fp16:
        data = sum(value << (16 * index) for index, value in enumerate(values))
        seed_word = seed
        expected_word = expected
    else:
        data = values[0] | (values[1] << 32)
        seed_word = seed
        expected_word = expected

    fields = [
        (int(fp16), 1),
        (rm, 3),
        (seed_word, 32),
        (data, 64),
        (active, 4),
        (expected_word, 32),
        (status, 5),
    ]
    packed = 0
    for value, width in fields:
        packed = (packed << width) | (value & ((1 << width) - 1))
    return packed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count-per-format", type=int, default=300)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xA4A2026)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "tb"
        / "fp_exact_reduction_oracle_vectors.mem",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    vectors: list[int] = []
    for fp16 in (False, True):
        for index in range(args.count_per_format):
            vectors.append(make_vector(rng, fp16, index % 5))

    digits = (VECTOR_WIDTH + 3) // 4
    args.output.write_text(
        "\n".join(f"{vector:0{digits}x}" for vector in vectors) + "\n",
        encoding="ascii",
    )
    print(
        f"wrote {len(vectors)} exact integer-oracle vectors to {args.output} "
        f"(seed={args.seed:#x})"
    )


if __name__ == "__main__":
    main()
