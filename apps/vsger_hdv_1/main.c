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

#define TOTAL_ELEMENTS 16384

#ifndef VSGER_HDV_TASK_ENTRY
#define VSGER_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// A[i,:] += (alpha * x[i]) * y[:]  (rank-1 update), m rows x n cols.
void vsger(int m, int n, const float a, const float *x, const float *y, float *A);

int main() {
    const float a = 6.66;
    // x, y, A must NOT alias: A is read-modify-written, so if x or y shared A's
    // buffer they would be corrupted mid-loop.  A = src1 (128x128), x = src2[0..127],
    // y = src2[128..255] are all disjoint.
    vsger(128, 128, a, src2, src2 + 128, src1);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vsger(int m, int n, const float a, const float *x, const float *y, float *A) {
    // ABI: a0=m, a1=n, fa0=alpha, a2=x, a3=y, a4=A.
    //
    // Nested loop.  Outer (row_loop) computes ft1 = alpha*x[i] (scalar FP, split
    // from its load-use); inner (col_loop) is a strip-mine that loads A/y chunks,
    // does vfmacc.vf (reads ft1 as scalar operand from a completed EP), and stores
    // back.  The inner body uses GEMM-style 256b packets: the two vector loads are
    // kept close to the loop head for prefetch visibility, while the store and
    // scalar pointer updates are packed after the FMA.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vsger_hdv_task_start:\n"

    // setup: row stride bytes + base pointers. a4 itself is the running matrix
    // row pointer, avoiding a one-instruction setup packet for an alias.
    "HDV_HINT 0x0a\n"
    "slli t6, a1, 2\n"
    "mv t0, a0\n"
    "mv t1, a2\n"

    // outer loop top: load x[i].
    "row_loop:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "flw ft0, 0(t1)\n"
    "nop\n"
    "nop\n"
    // alpha * x[i] (load-use of ft0).
    "HDV_HINT 0x00\n"
    "fmul.s ft1, fa0, ft0\n"
    "nop\n"
    "nop\n"
    // reset inner pointers / column counter.
    "HDV_HINT 0x0a\n"
    "mv t3, a3\n"
    "mv t4, a1\n"
    "mv t5, a4\n"

    // Two full-VL chunks per iteration for the representative N=128 shape.
    // v0/v1 and v2/v3 keep adjacent read-modify-write chains distinct. The 17
    // instructions occupy two 256-bit packets and one 128-bit packet exactly.
    "col_loop:\n"
    "HDV_HINT 0x802, 1, 1, 1, 0, 1\n"
    "vsetvli a5, t4, e32, m1, ta, ma\n"
    "vle32.v v0, (t3)\n"
    "vle32.v v1, (t5)\n"
    "slli a6, a5, 2\n"
    "vfmacc.vf v1, ft1, v0\n"
    "vse32.v v1, (t5)\n"
    "add t5, t5, a6\n"

    "HDV_HINT 0x822, 1, 1, 0, 0, 1\n"
    "add t3, t3, a6\n"
    "sub t4, t4, a5\n"
    "vle32.v v2, (t3)\n"
    "vle32.v v3, (t5)\n"
    "vfmacc.vf v3, ft1, v2\n"
    "vse32.v v3, (t5)\n"
    "add t5, t5, a6\n"

    "HDV_HINT 0x02, 0, 0, 0, 1\n"
    "add t3, t3, a6\n"
    "sub t4, t4, a5\n"
    "bnez t4, col_loop\n"

    // outer pointer bumps + row decrement.
    "HDV_HINT 0x0a\n"
    "addi t1, t1, 4\n"
    "add a4, a4, t6\n"
    "addi t0, t0, -1\n"
    // outer back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t0, row_loop\n"
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
