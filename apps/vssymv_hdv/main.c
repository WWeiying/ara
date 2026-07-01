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

#ifndef VSSYMV_HDV_TASK_ENTRY
#define VSSYMV_HDV_TASK_ENTRY 0x80001000UL
#endif

// ── Variant selector: BLAS_LMUL ─────────────────────────────────────────────
// BLAS_LMUL=1 : original m1 kernel, fixed 32x32 (VLMAX=32). default, validated.
// BLAS_LMUL=4 : unified m4 kernel, RUNTIME dim N<=128 (a3, +HDV_A3=N), sweepable.
// Only ONE compiles into .hdv_task (it becomes the entry).  Makefile: blas_lmul.
#ifndef BLAS_LMUL
#define BLAS_LMUL 1
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// m1 (original, fixed 32x32) and m4 (unified, runtime N).
void vssymv_f32_32x32(const float *A, const float *x, float *y,
                      const float alpha, const float beta);
void vssymv_f32(const float *A, const float *x, float *y, int n,
                const float alpha, const float beta);

int main() {
#if BLAS_LMUL == 1
    vssymv_f32_32x32(src1, src2, src1, 1.0f, 1.0f);
#else
    vssymv_f32(src1, src2, src1, 32, 1.0f, 1.0f);
#endif
    return 0;
}

#if BLAS_LMUL == 1
#include "vssymv_m1.inc"
#else
#include "blas_lmul.h"

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vssymv_f32(const float *A, const float *x, float *y, int total,
                const float alpha, const float beta) {
    // ── Prefetch-enabled m{2,4,8} form (parameterized original m1 strip-mine) ──
    // ABI: a0=A, a1=x, a2=y, a3=TOTAL elements (= rows*VLMAX), fa0=alpha, fa1=beta.
    //
    // Like the m1 .inc: the in-loop `vsetvli s0, t0` re-establishes VL each row
    // with AVL=t0 = remaining elements (starts high, decrements by VL).  avl>=2*vl
    // for all but the tail -> the A-row load prefetches at 1X (next row=next iter).
    // The in-loop vsetvli is REQUIRED: hoisting it to setup makes the HDV drop the
    // vector loads (they never reach the VLSU).  vregs LMUL-aligned (BL_G*).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vssymv_hdv_task_start:\n"

    // setup: config VL=VLMAX, load x; zero seed, total -> t0, A/y bases.
    "HDV_HINT 0x00\n"
    "li t3, " BL_STR(BLAS_LMUL) "*32\n"
    "vsetvli zero, t3, e32, m" BL_STR(BLAS_LMUL) ", ta, ma\n"
    "vle32.v v0, (a1)\n"
    "HDV_HINT 0x0a\n"
    "fmv.w.x ft0, zero\n"
    "mv t0, a3\n"
    "mv t1, a0\n"
    "HDV_HINT 0x02\n"
    "mv t2, a2\n"
    "nop\n"
    "nop\n"

    // row loop top: in-loop vsetvli (AVL=t0, high) || load A row (1X prefetch).
    "row_loop:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0, " BL_STR(BL_PFM) "\n"
    "vsetvli s0, t0, e32, m" BL_STR(BLAS_LMUL) ", ta, ma\n"
    "vle32.v v" BL_STR(BL_G1) ", (t1)\n"
    "nop\n"
    // A[i,:]*x || seed (vfmul writes G2, vfmv.v.f writes G3 — no conflict).
    "HDV_HINT 0x02\n"
    "vfmul.vv v" BL_STR(BL_G2) ", v" BL_STR(BL_G1) ", v0\n"
    "vfmv.v.f v" BL_STR(BL_G3) ", ft0\n"
    "nop\n"
    // reduce (separate EP from the seed to avoid a WAW bypass on the acc).
    "HDV_HINT 0x00\n"
    "vfredusum.vs v" BL_STR(BL_G3) ", v" BL_STR(BL_G2) ", v" BL_STR(BL_G3) "\n"
    "nop\n"
    "nop\n"
    // dot -> ft1 (vector->scalar writeback), and load y[i].
    "HDV_HINT 0x00\n"
    "vfmv.f.s ft1, v" BL_STR(BL_G3) "\n"
    "flw ft2, 0(t2)\n"
    "nop\n"
    // beta*y[i] (load-use of ft2).
    "HDV_HINT 0x00\n"
    "fmul.s ft2, ft2, fa1\n"
    "nop\n"
    "nop\n"
    // alpha*dot + beta*y[i] -> store.
    "HDV_HINT 0x00\n"
    "fmadd.s ft2, ft1, fa0, ft2\n"
    "fsw ft2, 0(t2)\n"
    "nop\n"
    // pointer bumps (A by VLMAX*4, y by 4) + remaining-elements decrement.
    "HDV_HINT 0x0a\n"
    "addi t1, t1, " BL_STR(BLAS_LMUL) "*128\n"
    "addi t2, t2, 4\n"
    "sub t0, t0, s0\n"
    // branch (loop_end).
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
