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

#ifndef FCONV2D_HDV_TASK_ENTRY
#define FCONV2D_HDV_TASK_ENTRY 0x80001000UL
#endif

extern const int64_t M;
extern const int64_t N;
extern const int64_t F;
extern double i[] __attribute__((aligned(4 * NR_LANES)));
extern double f[] __attribute__((aligned(4 * NR_LANES)));
extern double o[] __attribute__((aligned(4 * NR_LANES)));

// 3x3 2D convolution microkernel (offset-vle column shifts), HDV-packetised
// counterpart of fconv2d_asm.
void fconv2d_clean(double *o, double *in, double *flt, int64_t R, int64_t C,
                   int64_t Fdim);

int main() {
    fconv2d_clean(o, i, f, M, N, F);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void fconv2d_clean(double *o, double *in, double *flt, int64_t R, int64_t C,
                   int64_t Fdim) {
    // ABI: a0=o, a1=in, a2=flt, a3=R, a4=C, a5=Fdim.  e64/m2; v0=input chunk,
    // v8=accumulator.  Each "addi base,off ; vle" is split; each "vle || vfmacc"
    // is packed (Ara vector deps); the 9 filter loads are one-per-EP.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16))\n"
    ".endm\n"
    ".balign 16\n"
    "fconv2d_hdv_task_start:\n"

    // VL (one column block) + filter row stride.
    "HDV_HINT 0x02\n"
    "vsetvli t0, a4, e64, m2, ta, ma\n"
    "slli t6, a5, 3\n"
    "nop\n"
    // load 3x3 filter window (one fld per EP).
    "HDV_HINT 0x00\n"
    "fld ft0, 0(a2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft1, 8(a2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft2, 16(a2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "add t1, a2, t6\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft3, 0(t1)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft4, 8(t1)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft5, 16(t1)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "add t1, t1, t6\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft6, 0(t1)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft7, 8(t1)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fld ft8, 16(t1)\n"
    "nop\n"
    "nop\n"
    // strides + bases: ldi=(C+Fdim-1)*8, ldo=C*8.
    "HDV_HINT 0x0a\n"
    "add s0, a4, a5\n"
    "addi s0, s0, -1\n"
    "slli s0, s0, 3\n"
    "HDV_HINT 0x0a\n"
    "slli s1, a4, 3\n"
    "mv t1, a1\n"
    "mv t2, a0\n"
    "HDV_HINT 0x00\n"
    "mv t3, a3\n"
    "nop\n"
    "nop\n"

    // output-row loop.  Filter row 0: taps c+0,c+1,c+2.
    "fc_row:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "vle64.v v0, (t1)\n"
    "vfmul.vf v8, v0, ft0\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t4, t1, 8\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vle64.v v0, (t4)\n"
    "vfmacc.vf v8, ft1, v0\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t4, t1, 16\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vle64.v v0, (t4)\n"
    "vfmacc.vf v8, ft2, v0\n"
    "nop\n"
    // filter row 1.
    "HDV_HINT 0x00\n"
    "add t5, t1, s0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vle64.v v0, (t5)\n"
    "vfmacc.vf v8, ft3, v0\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t4, t5, 8\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vle64.v v0, (t4)\n"
    "vfmacc.vf v8, ft4, v0\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t4, t5, 16\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vle64.v v0, (t4)\n"
    "vfmacc.vf v8, ft5, v0\n"
    "nop\n"
    // filter row 2.
    "HDV_HINT 0x00\n"
    "add t5, t5, s0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vle64.v v0, (t5)\n"
    "vfmacc.vf v8, ft6, v0\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t4, t5, 8\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vle64.v v0, (t4)\n"
    "vfmacc.vf v8, ft7, v0\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t4, t5, 16\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vle64.v v0, (t4)\n"
    "vfmacc.vf v8, ft8, v0\n"
    "nop\n"
    // store output row + advance.
    "HDV_HINT 0x00\n"
    "vse64.v v8, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x0a\n"
    "add t1, t1, s0\n"
    "add t2, t2, s1\n"
    "addi t3, t3, -1\n"
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t3, fc_row\n"
    "nop\n"
    "nop\n"

    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
