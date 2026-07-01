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

#ifndef VSSYRK_HDV_TASK_ENTRY
#define VSSYRK_HDV_TASK_ENTRY 0x80001000UL
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
void ssyrk_f32_full_32x32x32(const float *A, float *C, const float alpha,
                             const float beta);
void ssyrk_f32_full(const float *A, float *C, int n, const float alpha,
                    const float beta);

int main() {
#if BLAS_LMUL == 1
    ssyrk_f32_full_32x32x32(src1, src2, 1.0f, 1.0f);
#else
    ssyrk_f32_full(src1, src2, 32, 1.0f, 1.0f);
#endif
    return 0;
}

#if BLAS_LMUL == 1
#include "vssyrk_m1.inc"
#else
__attribute__((naked, aligned(16), section(".hdv_task"),
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
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vssyrk_hdv_task_start:\n"

    // setup: N -> s0, VL=N (m4, once), stride s1 = N*4, counters + bases.
    "HDV_HINT 0x00\n"
    "mv s0, a2\n"
    "vsetvli zero, s0, e32, m4, ta, ma\n"
    "slli s1, a2, 2\n"
    "HDV_HINT 0x0a\n"
    "mv t0, s0\n"
    "mv t1, a0\n"
    "mv t2, a1\n"

    // outer loop top: acc = beta * C[i,:].
    ".balign 16\n"
    "row_loop:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "vle32.v v4, (t2)\n"
    "vfmul.vf v4, v4, fa1\n"
    "nop\n"
    // reset inner: column base (A[:,0]), a_ik base (A[i,0]), k counter.
    "HDV_HINT 0x0a\n"
    "mv t3, a0\n"
    "mv t4, t1\n"
    "mv a3, s0\n"

    // inner loop top: load scalar a_ik.
    ".balign 16\n"
    "k_loop:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "flw ft0, 0(t4)\n"
    "nop\n"
    "nop\n"
    // alpha * a_ik (load-use of ft0).
    "HDV_HINT 0x00\n"
    "fmul.s ft1, ft0, fa0\n"
    "nop\n"
    "nop\n"
    // strided load of column k (base t3, stride s1 = N*4).
    "HDV_HINT 0x00\n"
    "vlse32.v v0, (t3), s1\n"
    "nop\n"
    "nop\n"
    // acc += (alpha*a_ik) * A[:,k].
    "HDV_HINT 0x00\n"
    "vfmacc.vf v4, ft1, v0\n"
    "nop\n"
    "nop\n"
    // bump inner pointers + decrement k.
    "HDV_HINT 0x0a\n"
    "addi t3, t3, 4\n"
    "addi t4, t4, 4\n"
    "addi a3, a3, -1\n"
    // inner back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a3, k_loop\n"
    "nop\n"
    "nop\n"

    // store the full output row C[i,:].
    "HDV_HINT 0x00\n"
    "vse32.v v4, (t2)\n"
    "nop\n"
    "nop\n"
    // outer pointer bumps (by N*4) + row decrement.
    "HDV_HINT 0x0a\n"
    "add t1, t1, s1\n"
    "add t2, t2, s1\n"
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
#endif
