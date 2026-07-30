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

// 16-byte aligned HDV task entry used by the mock host/TB.
// Override with: make -C apps bin/vsdwt_hdv HDV_TASK_ENTRY=0x80002000
#ifndef VSDWT_HDV_TASK_ENTRY
#define VSDWT_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// In-place Haar DWT step: for each pair, (even,odd) -> ((e+o)/sqrt2, (e-o)/sqrt2)
void dwt_haar_hdv(float *even, float *odd, int n);

int main() {
    dwt_haar_hdv(src1, src2, TOTAL_ELEMENTS);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void dwt_haar_hdv(float *even, float *odd, int n) {
    // ABI on entry: a0 = even, a1 = odd, a2 = n (runtime element count, AVL).
    //
    // One-time setup runs as the first two EPs (count and the 1/sqrt(2) constant
    // in ft0), then the strip-mined loop follows.  The 0x3f3504f3 immediate is
    // emitted as explicit lui+addi so the packet layout is exact (li could expand
    // unpredictably).
    //
    // Loop packetisation (per iteration):
    //   256b packet 0:
    //     EP0 = vsetvli || vle(even) || vle(odd)
    //     EP1 = vfadd || vfsub || vfmul(low)
    //     EP2 = vfmul(high)
    //   256b packet 1:
    //     EP3 = vse(low) || vse(high)
    //     EP4 = slli || add even || add odd
    //     EP5 = sub
    //   loop-end packet:
    //     EP6 = bnez
    // Loads precede the in-place stores via EP order; the byte stride t2 is
    // produced before the pointer bumps in the same EP, and the count decrement
    // is still isolated from the branch by an EP boundary.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "dwt_haar_hdv_task_start:\n"

    // setup packet 0: loop count (runtime N from a2) + upper half of the constant.
    "HDV_HINT 0x0a\n"
    "mv t0, a2\n"
    "lui t6, 0x3f350\n"
    "addi t6, t6, 0x4f3\n"

    // setup packet 1: move the constant bit pattern into the FP register ft0.
    "HDV_HINT\n"
    "fmv.w.x ft0, t6\n"
    "nop\n"
    "nop\n"

    // loop body
    "dwt_loop:\n"
    "HDV_HINT 0x28a, 1, 0, 1, 0\n"
    "vsetvli t1, t0, e32, m1, ta, ma\n"
    "vle32.v v0, (a0)\n"
    "vle32.v v1, (a1)\n"
    "vfadd.vv v2, v0, v1\n"
    "vfsub.vv v3, v0, v1\n"
    "vfmul.vf v2, v2, ft0\n"
    "vfmul.vf v3, v3, ft0\n"

    "HDV_HINT 0x8a2, 1, 0, 0, 1\n"
    "vse32.v v2, (a0)\n"
    "vse32.v v3, (a1)\n"
    "slli t2, t1, 2\n"
    "add a0, a0, t2\n"
    "add a1, a1, t2\n"
    "sub t0, t0, t1\n"
    "bnez t0, dwt_loop\n"

    // ret remains in a separate packet and is reached only on loop fall-through.
    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
