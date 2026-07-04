#include <stdint.h>

#include "runtime.h"
#include "util.h"

#ifdef SPIKE
#include <stdio.h>
#elif defined ARA_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif

#define TOTAL_ELEMENTS 8192

#ifndef VSTENCIL3_HDV_TASK_ENTRY
#define VSTENCIL3_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// y[i] = a*x[i-1] + b*x[i] + c*x[i+1]
void vstencil3(int n, const float *x_center, float *y, float a, float b, float c);

int main() {
    const float a = 0.25f;
    const float b = 0.50f;
    const float c = 0.25f;

    vstencil3(TOTAL_ELEMENTS, src1 + 1, src2, a, b, c);
#ifndef SPIKE
    perf_time();
#endif

    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vstencil3(int n, const float *x_center, float *y, float a, float b, float c) {
    // ABI on entry: a0 = n, a1 = &x[1], a2 = y, fa0/fa1/fa2 = coefficients.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vstencil3_hdv_task_start:\n"

    "HDV_HINT 0x0a\n"
    "addi t3, a1, -4\n"
    "mv t4, a1\n"
    "addi t5, a1, 4\n"

    "HDV_HINT 0x00\n"
    "mv t6, a2\n"
    "nop\n"
    "nop\n"

    "stencil3_loop:\n"
    // Prefetch only the aligned left stream.  The three stencil streams are
    // separated by one FP32 element; prefetching all of them in the same tight
    // packet can leave stale neighboring entries at the lookup head before the
    // next iteration catches its matching prefetch.
    "HDV_HINT 0xa22, 1, 0, 1, 0, 0, 0\n"
    "vsetvli t0, a0, e32, m1, ta, ma\n"
    "vle32.v v0, (t3)\n"
    "slli t1, t0, 2\n"
    "sub a0, a0, t0\n"
    "vfmul.vf v8, v0, fa0\n"
    "nop\n"
    "nop\n"

    // Center/right are adjacent streams.  Enable their prefetch too so the
    // short/medium AVL points can use all three stencil streams.
    "HDV_HINT 0xa22, 1, 0, 0, 0, 0, 0\n"
    "vle32.v v1, (t4)\n"
    "vle32.v v2, (t5)\n"
    "vfmacc.vf v8, fa1, v1\n"
    "vfmacc.vf v8, fa2, v2\n"
    "vse32.v v8, (t6)\n"
    "add t3, t3, t1\n"
    "add t4, t4, t1\n"

    "HDV_HINT 0x02, 0, 0, 0, 0, 0, 1\n"
    "add t5, t5, t1\n"
    "add t6, t6, t1\n"
    "nop\n"

    "HDV_HINT 0x1f, 0, 0, 0, 1\n"
    "bnez a0, stencil3_loop\n"
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
