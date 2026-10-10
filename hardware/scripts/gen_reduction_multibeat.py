#!/usr/bin/env python3
"""Finite multi-beat exact sums with an integer reference and adversarial bins."""
import argparse
import random
from pathlib import Path
from gen_exact_reduction_oracle import (
    decode_fixed, finite_value, fp16_to_fp32_bits, is_zero, round_fixed, sign_bit,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--count", type=int, default=1500)
    parser.add_argument("--seed", type=lambda x: int(x, 0), default=0xA4A20261007)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    with args.output.open("w") as out:
        for test in range(args.count):
            kind = test % 3  # FP32, native FP16, FP16 widened to FP32
            fp16 = kind == 1
            count = 4 if fp16 else 2
            rm = (test // 3) % 5
            beats = rng.choice([1, 2, 3, 4, 5, 7, 8, 16, 31, 32, 64])
            mode = (test // 15) % 6
            seed = finite_value(rng, fp16)
            if mode == 0:
                seed = 0
            terms = []
            words = []
            source_exact = 0
            for beat in range(beats):
                values = []
                for element in range(count):
                    value = finite_value(rng, kind != 0)
                    if mode == 1:
                        value = 0x7BFF if kind != 0 else 0x7F7FFFFF
                    elif mode == 2:
                        # All values hit one exponent bin, with maximal local
                        # significand shift, then alternate signs across banks.
                        value = 0x3FFF if kind != 0 else 0x487FFFFF
                        value |= ((beat + element) % 2) << (15 if kind != 0 else 31)
                    elif mode == 3:
                        value = rng.choice([0, 1, 2, 0x3FF if kind != 0 else 0x7FFFFF])
                        value |= rng.randrange(2) << (15 if kind != 0 else 31)
                    elif mode == 4:
                        value = rng.randrange(2) << (15 if kind != 0 else 31)
                    if kind == 2:
                        value = fp16_to_fp32_bits(value)
                    values.append(value)
                active = rng.randrange(1 << count) if mode in (0, 3, 4) else (1 << count) - 1
                if mode == 5 and test % 2 == 0:
                    active = 0
                for index, value in enumerate(values):
                    if active & (1 << index):
                        terms.append(value)
                        source_exact += decode_fixed(value, fp16)
                word = sum(v << ((16 if fp16 else 32) * i) for i, v in enumerate(values))
                words.append((word, active))
            all_values = [seed] + terms
            if terms:
                result, status = round_fixed(
                    source_exact + decode_fixed(seed, fp16), rm, fp16,
                    any(not is_zero(v, fp16) for v in all_values),
                    any(is_zero(v, fp16) and not sign_bit(v, fp16) for v in all_values),
                    any(is_zero(v, fp16) and sign_bit(v, fp16) for v in all_values))
            else:
                result, status = seed, 0
            out.write(f"{int(fp16)} {rm} {seed:08x} {beats} "
                      f"{source_exact % (1 << 288):072x} {result:08x} {status:02x}\n")
            for word, active in words:
                out.write(f"{word:016x} {active:x}\n")
    print(f"wrote {args.count} multi-beat cases to {args.output}")


if __name__ == "__main__":
    main()
