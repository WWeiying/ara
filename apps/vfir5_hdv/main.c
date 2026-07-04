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

#ifndef VFIR5_HDV_TASK_ENTRY
#define VFIR5_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// y[i] = c0*x[i] + c1*x[i+1] + c2*x[i+2] + c3*x[i+3] + c4*x[i+4]
void vfir5(int n, const float *x, float *y, float c0, float c1, float c2,
           float c3, float c4);

int main() {
    const float c0 = 0.10f;
    const float c1 = 0.20f;
    const float c2 = 0.40f;
    const float c3 = 0.20f;
    const float c4 = 0.10f;

    vfir5(TOTAL_ELEMENTS, src1, src2, c0, c1, c2, c3, c4);
#ifndef SPIKE
    perf_time();
#endif

    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vfir5(int n, const float *x, float *y, float c0, float c1, float c2,
           float c3, float c4) {
    // ABI on entry: a0 = n, a1 = x, a2 = y, fa0..fa4 = tap coefficients.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vfir5_hdv_task_start:\n"

    "HDV_HINT 0x0a\n"
    "mv t3, a1\n"
    "addi a3, a1, 4\n"
    "addi a4, a1, 8\n"

    "HDV_HINT 0x0a\n"
    "addi a5, a1, 12\n"
    "addi a6, a1, 16\n"
    "mv t4, a2\n"

    "fir5_loop:\n"
    // 256b packet with prefetch enabled for the first two load streams:
    //   EP0 = vsetvli || vle(x[i]) || vle(x[i+1])
    //   EP1 = slli || sub || bump x[i]/x[i+1]
    // The cut before slli keeps t0 consumers after vsetvli writeback.
    "HDV_HINT 0xa8a, 1, 0, 1, 0, 0, 0\n"
    "vsetvli t0, a0, e32, m1, ta, ma\n"
    "vle32.v v0, (t3)\n"
    "vle32.v v1, (a3)\n"
    "slli t1, t0, 2\n"
    "sub a0, a0, t0\n"
    "add t3, t3, t1\n"
    "add a3, a3, t1\n"

    // 256b packet with prefetch disabled for the remaining three offset
    // streams.  pbits all set; issue width splits after four instructions.
    "HDV_HINT 0xaaa, 1, 0, 0, 0, 0, 1\n"
    "vle32.v v2, (a4)\n"
    "vle32.v v3, (a5)\n"
    "vle32.v v4, (a6)\n"
    "add a4, a4, t1\n"
    "add a5, a5, t1\n"
    "add a6, a6, t1\n"
    "vfmul.vf v8, v0, fa0\n"

    // 256b packet.  Keep the store after the four FMA slots; t4 is bumped in
    // the same EP as the store, after the store base has been snapshotted.
    "HDV_HINT 0xaaa, 1, 0, 0, 0, 0, 0\n"
    "vfmacc.vf v8, fa1, v1\n"
    "vfmacc.vf v8, fa2, v2\n"
    "vfmacc.vf v8, fa3, v3\n"
    "vfmacc.vf v8, fa4, v4\n"
    "vse32.v v8, (t4)\n"
    "add t4, t4, t1\n"
    "nop\n"

    "HDV_HINT 0x1f, 0, 0, 0, 1\n"
    "bnez a0, fir5_loop\n"
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
