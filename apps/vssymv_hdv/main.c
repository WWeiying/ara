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

#define TOTAL_ELEMENTS 4096

#ifndef VSSYMV_HDV_TASK_ENTRY
#define VSSYMV_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// y = alpha * (A * x) + beta * y, A is 32x32 row-major FP32.
void vssymv_f32_32x32(const float *A, const float *x, float *y,
                      const float alpha, const float beta);

int main() {
    vssymv_f32_32x32(src1, src2, src1, 1.0f, 1.0f);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vssymv_f32_32x32(const float *A, const float *x, float *y,
                      const float alpha, const float beta) {
    // ABI: a0=A, a1=x, a2=y, fa0=alpha, fa1=beta.
    //
    // Single strip-mine row loop.  Per row: dot(A[i,:], x) via vfmul+vfredusum,
    // move the reduction scalar to ft1 (5.1 vector->scalar writeback), then the
    // dependent scalar FP chain alpha*dot + beta*y[i] is split one-per-EP because
    // each step consumes the previous result (load-use / writeback hazards).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vssymv_hdv_task_start:\n"

    // setup A: li t3,32 ; vsetvli (config) ; vle x.
    "HDV_HINT 0x00\n"
    "li t3, 32\n"
    "vsetvli zero, t3, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    // setup B: zero seed ft0 ; row count ; A/y row pointers.
    "HDV_HINT 0x0a\n"
    "fmv.w.x ft0, zero\n"
    "li t0, 1024\n"
    "mv t1, a0\n"
    "HDV_HINT 0x02\n"
    "mv t2, a2\n"
    "nop\n"
    "nop\n"

    // row loop top: re-config VL || load A row.
    "row_loop:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "vsetvli s0, t0, e32, m1, ta, ma\n"
    "vle32.v v1, (t1)\n"
    "nop\n"
    // A[i,:]*x || seed — vfmul writes v2, vfmv.v.f writes v16 (no conflict).
    "HDV_HINT 0x02\n"
    "vfmul.vv v2, v1, v0\n"
    "vfmv.v.f v16, ft0\n"
    "nop\n"
    // reduce — separate EP: vfredusum reads v2, v16; writes v16.
    // Must be in different EP from vfmv.v.f to avoid WAW bypass on v16.
    "HDV_HINT 0x00\n"
    "vfredusum.vs v16, v2, v16\n"
    "nop\n"
    "nop\n"
    // dot -> ft1 (vector->scalar writeback): isolate so fmadd sees it.
    "HDV_HINT 0x00\n"
    "vfmv.f.s ft1, v16\n"
    "flw ft2, 0(t2)\n"
    "nop\n"
    // beta*y[i] (load-use of ft2): isolate.
    "HDV_HINT 0x00\n"
    "fmul.s ft2, ft2, fa1\n"
    "nop\n"
    "nop\n"
    // alpha*dot + beta*y[i] -> store.
    "HDV_HINT 0x00\n"
    "fmadd.s ft2, ft1, fa0, ft2\n"
    "fsw ft2, 0(t2)\n"
    "nop\n"
    // pointer bumps + row decrement.
    "HDV_HINT 0x0a\n"
    "addi t1, t1, 128\n"
    "addi t2, t2, 4\n"
    "sub t0, t0, s0\n"
    // branch (loop_end).
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t0, row_loop\n"
    "nop\n"
    "nop\n"

    // ret terminates the HDV task.
    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
