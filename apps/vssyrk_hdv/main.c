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

#ifndef VSSYRK_HDV_TASK_ENTRY
#define VSSYRK_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// C = alpha * A * A^T + beta * C, 32x32 row-major FP32.
void ssyrk_f32_full_32x32x32(const float *A, float *C, const float alpha,
                             const float beta);

int main() {
    ssyrk_f32_full_32x32x32(src1, src2, 1.0f, 1.0f);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void ssyrk_f32_full_32x32x32(const float *A, float *C, const float alpha,
                             const float beta) {
    // ABI: a0=A, a1=C, fa0=alpha, fa1=beta.
    //
    // Nested loop.  Outer (row_loop) seeds acc = beta*C[i,:]; inner (k_loop)
    // reads scalar a_ik, scales by alpha, and accumulates the strided column
    // A[:,k] via vfmacc.vf.  Scalar load-use (flw->fmul) and the strided-load
    // base bump are kept in separate EPs.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vssyrk_hdv_task_start:\n"

    // setup: VL config + row stride + counters + base pointers.
    "HDV_HINT 0x00\n"
    "li s0, 32\n"
    "vsetvli zero, s0, e32, m1, ta, ma\n"
    "li t5, 128\n"
    "HDV_HINT 0x0a\n"
    "li t0, 32\n"
    "mv t1, a0\n"
    "mv t2, a1\n"

    // outer loop top: acc = beta * C[i,:].
    "row_loop:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "vle32.v v4, (t2)\n"
    "vfmul.vf v4, v4, fa1\n"
    "nop\n"
    // reset inner pointers / k counter.
    "HDV_HINT 0x0a\n"
    "mv t3, a0\n"
    "mv t4, t1\n"
    "li a2, 32\n"

    // inner loop top: load scalar a_ik.
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
    // strided load of column k (base t3, stride t5).
    "HDV_HINT 0x00\n"
    "vlse32.v v0, (t3), t5\n"
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
    "addi a2, a2, -1\n"
    // inner back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a2, k_loop\n"
    "nop\n"
    "nop\n"

    // store the full output row C[i,:].
    "HDV_HINT 0x00\n"
    "vse32.v v4, (t2)\n"
    "nop\n"
    "nop\n"
    // outer pointer bumps + row decrement.
    "HDV_HINT 0x0a\n"
    "addi t1, t1, 128\n"
    "addi t2, t2, 128\n"
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
