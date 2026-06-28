// ============================================================================
// vsger_asm — tightly-coupled (standard Ara) counterpart of vsger_hdv.
// Auto-derived from the HDV version: HDV packetization stripped (HDV_HINT
// lui-x0 packet headers removed; .hdv_task section -> .text naked function).
// Identical vector instruction stream; the scalar core issues vector ops
// directly to Ara (no decoupled front-end / no software prefetch hints).
// For main-branch tightly-coupled architecture testing.  NOT yet tested.
// ============================================================================
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

#define TOTAL_ELEMENTS 1024

#ifndef VSGER_HDV_TASK_ENTRY
#define VSGER_HDV_TASK_ENTRY 0x80001000UL
#endif

// Uniform AVL knob: build with `make bin/vsger_asm asm_avl=<n>` to sweep the
// rank-1 update column dimension n (the inner strip-mine AVL / runtime
// dimension N, matching +HDV_A1=<n> in the HDV sweep) the kernel is CALLED
// with.  The row count m stays fixed.  Defaults to 128 so a plain make is
// byte-identical to before.
#ifndef ASM_AVL
#define ASM_AVL 128
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
    HW_CNT_READY;
#ifndef SPIKE
    perf_time();
#endif
    vsger(128, ASM_AVL, a, src2, src2 + 128, src1);
#ifndef SPIKE
    perf_time();
#endif
    HW_CNT_NOT_READY;
    return 0;
}

__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void vsger(int m, int n, const float a, const float *x, const float *y, float *A) {
    // ABI: a0=m, a1=n, fa0=alpha, a2=x, a3=y, a4=A.
    //
    // Nested loop.  Outer (row_loop) computes ft1 = alpha*x[i] (scalar FP, split
    // from its load-use); inner (col_loop) is a strip-mine that loads A/y chunks,
    // does vfmacc.vf (reads ft1 as scalar operand from a completed EP), and stores
    // back.  vsetvli rd=a5 is read by slli in a LATER EP (A2-safe).  Both loop
    // back-edges sit in their own EP (loop_end marker).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsger_hdv_task_start:\n"

    // setup: row stride bytes + base pointers.
    "slli t6, a1, 2\n"
    "mv t0, a0\n"
    "mv t1, a2\n"
    "mv t2, a4\n"
    "nop\n"
    "nop\n"

    // outer loop top: load x[i].
    "row_loop:\n"
    "flw ft0, 0(t1)\n"
    "nop\n"
    "nop\n"
    // alpha * x[i] (load-use of ft0).
    "fmul.s ft1, fa0, ft0\n"
    "nop\n"
    "nop\n"
    // reset inner pointers / column counter.
    "mv t3, a3\n"
    "mv t4, a1\n"
    "mv t5, t2\n"

    // inner loop top: VL config || load y chunk.
    "col_loop:\n"
    "vsetvli a5, t4, e32, m1, ta, ma\n"
    "vle32.v v0, (t3)\n"
    "nop\n"
    // load A chunk.
    "vle32.v v1, (t5)\n"
    "nop\n"
    "nop\n"
    // byte stride from granted VL (a5 writeback already landed).
    "slli a6, a5, 2\n"
    "nop\n"
    "nop\n"
    // A += (alpha*x[i]) * y.
    "vfmacc.vf v1, ft1, v0\n"
    "nop\n"
    "nop\n"
    // store old A chunk || bump A pointer.
    "vse32.v v1, (t5)\n"
    "add t5, t5, a6\n"
    "nop\n"
    // bump y pointer || decrement column counter.
    "add t3, t3, a6\n"
    "sub t4, t4, a5\n"
    "nop\n"
    // inner back-edge.
    "bnez t4, col_loop\n"
    "nop\n"
    "nop\n"

    // outer pointer bumps + row decrement.
    "addi t1, t1, 4\n"
    "add t2, t2, t6\n"
    "addi t0, t0, -1\n"
    // outer back-edge.
    "bnez t0, row_loop\n"
    "nop\n"
    "nop\n"

    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
