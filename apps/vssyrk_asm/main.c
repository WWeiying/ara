// ============================================================================
// vssyrk_asm — tightly-coupled (standard Ara) counterpart of vssyrk_hdv.
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

#ifndef VSSYRK_HDV_TASK_ENTRY
#define VSSYRK_HDV_TASK_ENTRY 0x80001000UL
#endif

// ── Variant selector: BLAS_LMUL ─────────────────────────────────────────────
// BLAS_LMUL=1 : original m1 kernel, fixed 32x32 (VLMAX=32). default, validated.
// BLAS_LMUL=4 : unified m4 kernel, RUNTIME dim N<=128 (a2, +HDV_A2=N), sweepable.
#ifndef BLAS_LMUL
#define BLAS_LMUL 1
#endif

// ── Uniform sweep knob: ASM_AVL ─────────────────────────────────────────────
// Mirrors the _hdv runtime +HDV_A2=N override on the tightly-coupled build.
// Default = the literal dimension main() passed before (32); plain `make`
// (no asm_avl=) is byte-identical to before.  Only the BLAS_LMUL==4 (m4)
// runtime-dimension kernel call uses it; the m1 fixed 32x32 call is untouched.
#ifndef ASM_AVL
#define ASM_AVL 32
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// m1 (original, fixed 32x32) and m4 (unified, runtime N).
void ssyrk_f32_full_32x32x32(const float *A, float *C, const float alpha,
                             const float beta);
void ssyrk_f32_full(const float *A, float *C, int n, const float alpha,
                    const float beta);

int main() {
    HW_CNT_READY;
#ifndef SPIKE
    perf_time();
#endif
#if BLAS_LMUL == 1
    ssyrk_f32_full_32x32x32(src1, src2, 1.0f, 1.0f);
#else
    ssyrk_f32_full(src1, src2, ASM_AVL, 1.0f, 1.0f);
#endif
#ifndef SPIKE
    perf_time();
#endif
    HW_CNT_NOT_READY;
    return 0;
}

#if BLAS_LMUL == 1
#include "vssyrk_m1.inc"
#else
__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void ssyrk_f32_full(const float *A, float *C, int n, const float alpha,
                    const float beta) {
    // ── Unified BLAS form (parameterized N, sweepable) ───────────────────────
    // ABI: a0=A, a1=C, a2=N, fa0=alpha, fa1=beta.  avl_sweep injects +HDV_A2=N.
    //
    // Strategy (shared by the whole B-tier): set VL ONCE in setup with LMUL=m4
    // (VLMAX = VLEN/SEW*4 = 1024/32*4 = 128), so one vector group holds a full
    // N-element row for any N<=128 — no per-iteration vsetvli (which is what
    // deadlocks the front-end via high-AVL prefetch) and no column strip-mine.
    // The row/column stride (N*4 bytes) is computed at runtime via slli; every
    // loop top is .balign 16 so the IPU sees a PacketBytes-aligned redirect_pc.
    //
    // C[i,:] = beta*C[i,:] + sum_k alpha*A[i,k] * A[:,k]  (A[:,k] = strided col).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vssyrk_hdv_task_start:\n"
    "addi sp, sp, -16\n"
    "sd s0, 0(sp)\n"
    "sd s1, 8(sp)\n"

    // setup: N -> s0, VL=N (m4, once), stride s1 = N*4, counters + bases.
    "mv s0, a2\n"
    "vsetvli zero, s0, e32, m4, ta, ma\n"
    "slli s1, a2, 2\n"
    "mv t0, s0\n"
    "mv t1, a0\n"
    "mv t2, a1\n"

    // outer loop top: acc = beta * C[i,:].
    ".balign 16\n"
    "row_loop:\n"
    "vle32.v v4, (t2)\n"
    "vfmul.vf v4, v4, fa1\n"
    "nop\n"
    // reset inner: column base (A[:,0]), a_ik base (A[i,0]), k counter.
    "mv t3, a0\n"
    "mv t4, t1\n"
    "mv a3, s0\n"

    // inner loop top: load scalar a_ik.
    ".balign 16\n"
    "k_loop:\n"
    "flw ft0, 0(t4)\n"
    "nop\n"
    "nop\n"
    // alpha * a_ik (load-use of ft0).
    "fmul.s ft1, ft0, fa0\n"
    "nop\n"
    "nop\n"
    // strided load of column k (base t3, stride s1 = N*4).
    "vlse32.v v0, (t3), s1\n"
    "nop\n"
    "nop\n"
    // acc += (alpha*a_ik) * A[:,k].
    "vfmacc.vf v4, ft1, v0\n"
    "nop\n"
    "nop\n"
    // bump inner pointers + decrement k.
    "addi t3, t3, 4\n"
    "addi t4, t4, 4\n"
    "addi a3, a3, -1\n"
    // inner back-edge.
    "bnez a3, k_loop\n"
    "nop\n"
    "nop\n"

    // store the full output row C[i,:].
    "vse32.v v4, (t2)\n"
    "nop\n"
    "nop\n"
    // outer pointer bumps (by N*4) + row decrement.
    "add t1, t1, s1\n"
    "add t2, t2, s1\n"
    "addi t0, t0, -1\n"
    // outer back-edge.
    "bnez t0, row_loop\n"
    "nop\n"
    "nop\n"

    "ld s0, 0(sp)\n"
    "ld s1, 8(sp)\n"
    "addi sp, sp, 16\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
#endif
