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

// 16-byte aligned HDV task entry used by the mock host/TB.
// Override with: make -C apps bin/vsswap_hdv HDV_TASK_ENTRY=0x80002000
#ifndef VSSWAP_HDV_TASK_ENTRY
#define VSSWAP_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// swap: x[i] <-> y[i]
void vsswap(int n, float *x, float *y);

int main() {
    vsswap(TOTAL_ELEMENTS, src1, src2);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vsswap(int n, float *x, float *y) {
    // ABI on entry: a0 = n, a1 = x, a2 = y.
    //
    // HDV packetisation (4 EPs per loop iteration):
    //   EP0 = vsetvli || vle(v0,x) || vle(v1,y)
    //   EP1 = sub || slli || vse(v1->x)
    //   EP2 = vse(v0->y) || add a1 || add a2
    //   EP3 = bnez
    // Both source vectors are loaded in EP0 before either store; EP ordering
    // guarantees load-before-store to the same address (EP0 < EP1/EP2), so Ara
    // sees the loads ahead of the swaps.  Pointer bumps happen after the stores.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vsswap_hdv_task_start:\n"

    "loop:\n"
    "HDV_HINT 0x0a, 0, 0, 1, 0\n"
    "vsetvli t0, a0, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "vle32.v v1, (a2)\n"

    "HDV_HINT 0x0a\n"
    "sub a0, a0, t0\n"
    "slli t1, t0, 2\n"
    "vse32.v v1, (a1)\n"

    "HDV_HINT 0x0a, 0, 0, 0, 1\n"
    "vse32.v v0, (a2)\n"
    "add a1, a1, t1\n"
    "add a2, a2, t1\n"

    "HDV_HINT\n"
    "bnez a0, loop\n"
    "ret\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
