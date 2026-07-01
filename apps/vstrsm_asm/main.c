// ============================================================================
// vstrsm_asm — tightly-coupled (standard Ara) counterpart of vstrsm_hdv.
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

#define TOTAL_ELEMENTS 32768

#ifndef VSTRSM_HDV_TASK_ENTRY
#define VSTRSM_HDV_TASK_ENTRY 0x80001000UL
#endif

// ── Variant selector: BLAS_LMUL ─────────────────────────────────────────────
// BLAS_LMUL=1 : original m1 kernel, fixed 32x32 (VLMAX=32). default, validated.
// BLAS_LMUL=4 : unified m4 kernel, RUNTIME dim N<=128 (a2, +HDV_A2=N), sweepable.
#ifndef BLAS_LMUL
#define BLAS_LMUL 1
#endif

// ── Uniform AVL knob ────────────────────────────────────────────────────────
// ASM_AVL parameterizes the RUNTIME dimension passed to the m4 (#else) kernel
// call.  Default = 32 (the value hard-coded today), so a plain `make` is
// byte-identical.  Injected via -DASM_AVL=<n> by `make ... asm_avl=<n>`.
#ifndef ASM_AVL
#define ASM_AVL 32
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// m1 (original, fixed 32x32) and m4 (unified, runtime N).
void strsm_f32_left_lower_32x32(const float *L, float *B);
void strsm_f32_left_lower(const float *L, float *B, int n);

int main() {
    HW_CNT_READY;
#ifndef SPIKE
    perf_time();
#endif
#if BLAS_LMUL == 1
    strsm_f32_left_lower_32x32(src1, src2);
#else
    strsm_f32_left_lower(src1, src2, ASM_AVL);
#endif
#ifndef SPIKE
    perf_time();
#endif
    HW_CNT_NOT_READY;
    return 0;
}

#if BLAS_LMUL == 1
#include "vstrsm_m1.inc"
#else
#include "blas_lmul.h"
__attribute__((naked, 
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
    ".balign 16\n"
    "vstrsm_hdv_task_start:\n"
    "addi sp, sp, -16\n"
    "sd s0, 0(sp)\n"
    "sd s1, 8(sp)\n"

    // setup: AVL = VLMAX (avl=vl, so the HDV doesn't fault on this kernel), stride
    // s1 = VLMAX*4, i index, bases, M row count.
    "li s0, " BL_STR(BLAS_LMUL) "*32\n"
    "vsetvli zero, s0, e32, m" BL_STR(BLAS_LMUL) ", ta, ma\n"
    "li s1, " BL_STR(BLAS_LMUL) "*128\n"
    "li t0, 0\n"
    "mv t1, a0\n"
    "mv t2, a1\n"
    "mv t6, a2\n"
    "nop\n"
    "nop\n"

    // outer loop top: diagonal address = &L[i][i] = L[i,:] + i*4.
    ".balign 16\n"
    "row_loop:\n"
    "slli t4, t0, 2\n"
    "add t3, t1, t4\n"
    "nop\n"
    // load the diagonal element.
    "flw fa0, 0(t3)\n"
    "nop\n"
    "nop\n"
    // load RHS row, divide by diag via scalar reciprocal, store back.
    "vle32.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    "li a5, 0x3f800000\n"
    "fmv.w.x ft2, a5\n"
    "nop\n"
    "fdiv.s ft2, ft2, fa0\n"
    "nop\n"
    "nop\n"
    "vfmul.vf v0, v0, ft2\n"
    "nop\n"
    "nop\n"
    "vse32.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    // set up the below-rows update: next L/B rows (by VLMAX*4) + remaining count.
    "add t5, t1, s1\n"
    "add a3, t2, s1\n"
    "addi a4, t6, -1\n"
    // skip the inner loop when no rows remain below.
    "beqz a4, update_done\n"
    "nop\n"
    "nop\n"

    // inner loop top: &L[j][i] = L[j,:] + i*4, then L[j][i].
    ".balign 16\n"
    "update_loop:\n"
    "add a5, t5, t4\n"
    "nop\n"
    "nop\n"
    "flw fa1, 0(a5)\n"
    "nop\n"
    "nop\n"
    // B[j,:] re-stream load.
    "vle32.v v" BL_STR(BL_G1) ", (a3)\n"
    "nop\n"
    "nop\n"
    "vfnmsac.vf v" BL_STR(BL_G1) ", fa1, v0\n"
    "nop\n"
    "nop\n"
    "vse32.v v" BL_STR(BL_G1) ", (a3)\n"
    "nop\n"
    "nop\n"
    // bump inner L/B pointers (by VLMAX*4) + decrement count.
    "add t5, t5, s1\n"
    "add a3, a3, s1\n"
    "addi a4, a4, -1\n"
    // inner back-edge.
    "bnez a4, update_loop\n"
    "nop\n"
    "nop\n"

    // outer pointer bumps (by VLMAX*4) + index/row updates.
    ".balign 16\n"
    "update_done:\n"
    "add t1, t1, s1\n"
    "add t2, t2, s1\n"
    "addi t0, t0, 1\n"
    "addi t6, t6, -1\n"
    "nop\n"
    "nop\n"
    // outer back-edge.
    "bnez t6, row_loop\n"
    "nop\n"
    "nop\n"

    "ld s0, 0(sp)\n"
    "ld s1, 8(sp)\n"
    "addi sp, sp, 16\n"
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
    ".option pop\n"
    );
}
#endif
