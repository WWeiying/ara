#!/usr/bin/env python3
# Parameterized BLAS data generator for the HDV sweep.
#
# Emits .data.src1 / .data.src2 (+ optional .data.dest) sections of random FP32
# words, sized for a problem dimension N.  The arrays are generated ONCE at the
# sweep's maximum N (default 128) so the linked src1/src2 addresses stay fixed;
# the avl_sweep.sh then varies the *runtime* dimension via the scalar backend's
# +HDV_A<k> plusarg (no re-link, no per-point data regen).  See avl_sweep.sh.
#
# Shapes (what each section must hold for the kernel's worst case = N_max):
#   square  : src1 = N^2 (matrix A/L), src2 = N^2 (matrix C/B, or vectors)
#   matvec  : src1 = N^2 (matrix A),   src2 = N^2 (covers x,y vectors w/ slack)
#   ger     : src1 = N^2 (matrix A),   src2 = N^2 (covers x,y vectors w/ slack)
#   gemm    : src1 = N^2 (A),          src2 = N^2 (B)   (C aliases src1)
#
# Usage:
#   gen_blas.py --n 128 --shape square            # both arrays = 128*128 words
#   gen_blas.py --src1-size 16384 --src2-size 16384   # explicit override
import argparse
import random


def emit_array(f, name, n_words, elem_bytes=4):
    f.write(f".section .data.{name}\n")
    f.write(f".align {elem_bytes}\n")
    f.write(f".global {name}\n")
    f.write(f"{name}:\n")
    for _ in range(n_words):
        word = '0x' + ''.join(random.choices('0123456789ABCDEF', k=2 * elem_bytes))
        f.write(f"\t.word {word}\n")
    f.write(f".global _{name}_size\n")
    f.write(f"_{name}_size:\n")
    f.write(f"\t.word {n_words}\n\n")


def main():
    p = argparse.ArgumentParser(description="parameterized BLAS data.S generator")
    p.add_argument("--n", type=int, default=128, help="problem dimension N (square N x N)")
    p.add_argument("--shape", default="square",
                   choices=["square", "matvec", "ger", "gemm"],
                   help="data shape (decides per-array word counts)")
    p.add_argument("--src1-size", type=int, default=None, help="override src1 words")
    p.add_argument("--src2-size", type=int, default=None, help="override src2 words")
    p.add_argument("--dest-size", type=int, default=0, help="optional dest words")
    p.add_argument("-o", "--output", default="data.S", help="output file")
    args = p.parse_args()

    # All current BLAS shapes need at most N^2 per source array; generating both
    # at N^2 keeps a uniform layout (and gives vector operands ample slack).
    n2 = args.n * args.n
    s1 = args.src1_size if args.src1_size is not None else n2
    s2 = args.src2_size if args.src2_size is not None else n2

    with open(args.output, "w") as f:
        emit_array(f, "src1", s1)
        emit_array(f, "src2", s2)
        if args.dest_size > 0:
            emit_array(f, "dest", args.dest_size)


if __name__ == "__main__":
    main()
