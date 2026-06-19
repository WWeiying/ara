#include <stdint.h>
#include <string.h>

#include "runtime.h"
#include "util.h"

#ifdef SPIKE
#include <stdio.h>
#elif defined ARA_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif

extern const int64_t M;
extern const int64_t N;
extern const int64_t F;
extern double i[] __attribute__((aligned(4 * NR_LANES)));
extern double f[] __attribute__((aligned(4 * NR_LANES)));
extern double o[] __attribute__((aligned(4 * NR_LANES)));

// 3x3 2D convolution microkernel over one e64/m2 column block.  Column shifts
// are done with offset vle loads (not vslidedown), so it is dead simple and
// correct; the 3x3 filter window is the top-left 3x3 of the stored F-wide
// filter, the input keeps its real (N+F-1) padded row stride.  Plain-Ara
// baseline of fconv2d_hdv.  (Repo's optimised fconv2d_3x3/7x7 = Ara upper bound.)
void fconv2d_clean(double *o, double *in, double *flt, int64_t R, int64_t C,
                   int64_t Fdim);

int main() {
    fconv2d_clean(o, i, f, M, N, F);
    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void fconv2d_clean(double *o, double *in, double *flt, int64_t R, int64_t C,
                   int64_t Fdim) {
    // ABI: a0=o, a1=in, a2=flt, a3=R, a4=C, a5=Fdim.  ldi = (C+Fdim-1)*8.
    // 9 filter taps -> ft0..ft8 (rows of the stored filter are Fdim wide).
    __asm__ volatile (
        "vsetvli t0, a4, e64, m2, ta, ma\n"   // VL columns (one block)
        // load the 3x3 filter window (filter row stride = Fdim*8).
        "slli t6, a5, 3\n"                    // Fdim*8
        "fld ft0, 0(a2)\n"
        "fld ft1, 8(a2)\n"
        "fld ft2, 16(a2)\n"
        "add t1, a2, t6\n"
        "fld ft3, 0(t1)\n"
        "fld ft4, 8(t1)\n"
        "fld ft5, 16(t1)\n"
        "add t1, t1, t6\n"
        "fld ft6, 0(t1)\n"
        "fld ft7, 8(t1)\n"
        "fld ft8, 16(t1)\n"
        // strides: ldi = (C+Fdim-1)*8, ldo = C*8.
        "add s0, a4, a5\n"
        "addi s0, s0, -1\n"
        "slli s0, s0, 3\n"
        "slli s1, a4, 3\n"
        "mv t1, a1\n"                         // input window base, row r
        "mv t2, a0\n"                         // output base
        "mv t3, a3\n"                         // output-row counter
        "fc_row:\n"
        // filter row 0: i[r+0][c+0..2].
        "vle64.v v0, (t1)\n"
        "vfmul.vf v8, v0, ft0\n"
        "addi t4, t1, 8\n"
        "vle64.v v0, (t4)\n"
        "vfmacc.vf v8, ft1, v0\n"
        "addi t4, t1, 16\n"
        "vle64.v v0, (t4)\n"
        "vfmacc.vf v8, ft2, v0\n"
        // filter row 1: i[r+1][c+0..2].
        "add t5, t1, s0\n"
        "vle64.v v0, (t5)\n"
        "vfmacc.vf v8, ft3, v0\n"
        "addi t4, t5, 8\n"
        "vle64.v v0, (t4)\n"
        "vfmacc.vf v8, ft4, v0\n"
        "addi t4, t5, 16\n"
        "vle64.v v0, (t4)\n"
        "vfmacc.vf v8, ft5, v0\n"
        // filter row 2: i[r+2][c+0..2].
        "add t5, t5, s0\n"
        "vle64.v v0, (t5)\n"
        "vfmacc.vf v8, ft6, v0\n"
        "addi t4, t5, 8\n"
        "vle64.v v0, (t4)\n"
        "vfmacc.vf v8, ft7, v0\n"
        "addi t4, t5, 16\n"
        "vle64.v v0, (t4)\n"
        "vfmacc.vf v8, ft8, v0\n"
        // store output row, advance.
        "vse64.v v8, (t2)\n"
        "add t1, t1, s0\n"
        "add t2, t2, s1\n"
        "addi t3, t3, -1\n"
        "bnez t3, fc_row\n"
        "ret\n"
    );
}
