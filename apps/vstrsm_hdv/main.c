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

#ifndef VSTRSM_HDV_TASK_ENTRY
#define VSTRSM_HDV_TASK_ENTRY 0x80001000UL
#endif

// ── Variant selector: BLAS_LMUL ─────────────────────────────────────────────
// BLAS_LMUL=1 : original m1 kernel, fixed 32x32 (VLMAX=32). default, validated.
// BLAS_LMUL=4 : unified m4 kernel, RUNTIME dim N<=128 (a2, +HDV_A2=N), sweepable.
#ifndef BLAS_LMUL
#define BLAS_LMUL 1
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// m1 (original, fixed 32x32) and m4 (unified, runtime N).
void strsm_f32_left_lower_32x32(const float *L, float *B);
void strsm_f32_left_lower(const float *L, float *B, int n);

int main() {
#if BLAS_LMUL == 1
    strsm_f32_left_lower_32x32(src1, src2);
#else
    strsm_f32_left_lower(src1, src2, 32);
#endif
    return 0;
}

#if BLAS_LMUL == 1
#include "vstrsm_m1.inc"
#else
#include "blas_lmul.h"
__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void strsm_f32_left_lower(const float *L, float *B, int m) {
    // ── m{2,4,8} form (demand-only, NO prefetch) ─────────────────────────────
    // ABI: a0=L, a1=B, a2=M(rows, <=VLMAX).  +HDV_A2=M.
    //
    // RHS width = VLMAX; v0 = pivot X[i,:], v(BL_G1) = B[j,:].  Unlike vssymv/
    // vsgemv this kernel CANNOT use the high-AVL prefetch trick: its two-loop +
    // vector-store (vse) structure faults under the HDV whenever avl>vl, so it
    // must run at avl=vl=VLMAX (no prefetch), like the original m1.
    //
    // for i: X[i,:] = B[i,:] / L[i,i];  for j>i: B[j,:] -= L[j,i] * X[i,:].
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vstrsm_hdv_task_start:\n"

    // setup: AVL = VLMAX (avl=vl, so the HDV doesn't fault on this kernel), stride
    // s1 = VLMAX*4, i index, bases, M row count.
    "HDV_HINT 0x00\n"
    "li s0, " BL_STR(BLAS_LMUL) "*32\n"
    "vsetvli zero, s0, e32, m" BL_STR(BLAS_LMUL) ", ta, ma\n"
    "li s1, " BL_STR(BLAS_LMUL) "*128\n"
    "HDV_HINT 0x0a\n"
    "li t0, 0\n"
    "mv t1, a0\n"
    "mv t2, a1\n"
    "HDV_HINT 0x00\n"
    "mv t6, a2\n"
    "nop\n"
    "nop\n"

    // outer loop top: diagonal address = &L[i][i] = L[i,:] + i*4.
    ".balign 16\n"
    "row_loop:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "slli t4, t0, 2\n"
    "add t3, t1, t4\n"
    "nop\n"
    // load the diagonal element.
    "HDV_HINT 0x00\n"
    "flw fa0, 0(t3)\n"
    "nop\n"
    "nop\n"
    // load RHS row, divide by diag, store back.
    "HDV_HINT 0x00\n"
    "vle32.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vfdiv.vf v0, v0, fa0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse32.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    // set up the below-rows update: next L/B rows (by VLMAX*4) + remaining count.
    "HDV_HINT 0x0a\n"
    "add t5, t1, s1\n"
    "add a3, t2, s1\n"
    "addi a4, t6, -1\n"
    // skip the inner loop when no rows remain below.
    "HDV_HINT 0x00\n"
    "beqz a4, update_done\n"
    "nop\n"
    "nop\n"

    // inner loop top: &L[j][i] = L[j,:] + i*4, then L[j][i].
    ".balign 16\n"
    "update_loop:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "add a5, t5, t4\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "flw fa1, 0(a5)\n"
    "nop\n"
    "nop\n"
    // B[j,:] re-stream load.
    "HDV_HINT 0x00\n"
    "vle32.v v" BL_STR(BL_G1) ", (a3)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vfnmsac.vf v" BL_STR(BL_G1) ", fa1, v0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse32.v v" BL_STR(BL_G1) ", (a3)\n"
    "nop\n"
    "nop\n"
    // bump inner L/B pointers (by VLMAX*4) + decrement count.
    "HDV_HINT 0x0a\n"
    "add t5, t5, s1\n"
    "add a3, a3, s1\n"
    "addi a4, a4, -1\n"
    // inner back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a4, update_loop\n"
    "nop\n"
    "nop\n"

    // outer pointer bumps (by VLMAX*4) + index/row updates.
    ".balign 16\n"
    "update_done:\n"
    "HDV_HINT 0x0a\n"
    "add t1, t1, s1\n"
    "add t2, t2, s1\n"
    "addi t0, t0, 1\n"
    "HDV_HINT 0x00\n"
    "addi t6, t6, -1\n"
    "nop\n"
    "nop\n"
    // outer back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t6, row_loop\n"
    "nop\n"
    "nop\n"

    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    // Front-end runahead pad: at m4 the IPU LINEARLY prefetches PAST the ret into
    // the .data the linker places right after .hdv_task, decodes a random float
    // word as a branch to a non-16B-aligned PC, and faults the front-end (hang).
    // A self-loop can't help (the prefetch overshoots the branch); instead pad
    // with enough nops that the prefetch window only ever sees nops until the ret
    // retires and ends the task.
    ".rept 48\n"
    "nop\n"
    ".endr\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
#endif
