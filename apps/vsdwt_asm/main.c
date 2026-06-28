// ============================================================================
// vsdwt_asm — tightly-coupled (standard Ara) counterpart of vsdwt_hdv.
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

#define TOTAL_ELEMENTS 4096

// 16-byte aligned HDV task entry used by the mock host/TB.
// Override with: make -C apps bin/vsdwt_hdv HDV_TASK_ENTRY=0x80002000
#ifndef VSDWT_HDV_TASK_ENTRY
#define VSDWT_HDV_TASK_ENTRY 0x80001000UL
#endif

// Uniform AVL knob injected by the build system via -DASM_AVL=<n>
// (make bin/vsdwt_asm asm_avl=<n>).  Defaults to TOTAL_ELEMENTS so a plain
// make reproduces the original hard-coded problem size byte-for-byte.
#ifndef ASM_AVL
#define ASM_AVL TOTAL_ELEMENTS
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// In-place Haar DWT step: for each pair, (even,odd) -> ((e+o)/sqrt2, (e-o)/sqrt2)
void dwt_haar_hdv(float *even, float *odd, int n);

int main() {
    HW_CNT_READY;
    #ifndef SPIKE
    perf_time();
    #endif
    dwt_haar_hdv(src1, src2, ASM_AVL);
    #ifndef SPIKE
    perf_time();
    #endif
    HW_CNT_NOT_READY;

    return 0;
}

__attribute__((naked, 
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
    //   EP0 = vsetvli || vle(v0,even) || vle(v1,odd)
    //   EP1 = vfadd(v2) || vfsub(v3) || vfmul(v2,ft0)
    //   EP2 = vfmul(v3,ft0) || vse(v2->even) || vse(v3->odd)
    //   EP3 = slli || add even || add odd
    //   EP4 = sub
    //   EP5 = bnez
    // Loads precede the in-place stores via EP order; the byte stride t2 produced
    // in EP3 is consumed by the pointer bumps in slot order.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "dwt_haar_hdv_task_start:\n"

    // setup packet 0: loop count (runtime N from a2) + upper half of the constant.
    "mv t0, a2\n"
    "lui t6, 0x3f350\n"
    "addi t6, t6, 0x4f3\n"

    // setup packet 1: move the constant bit pattern into the FP register ft0.
    "fmv.w.x ft0, t6\n"
    "nop\n"
    "nop\n"

    // loop body
    "dwt_loop:\n"
    "vsetvli t1, t0, e32, m1, ta, ma\n"
    "vle32.v v0, (a0)\n"
    "vle32.v v1, (a1)\n"

    "vfadd.vv v2, v0, v1\n"
    "vfsub.vv v3, v0, v1\n"
    "vfmul.vf v2, v2, ft0\n"

    "vfmul.vf v3, v3, ft0\n"
    "vse32.v v2, (a0)\n"
    "vse32.v v3, (a1)\n"

    "slli t2, t1, 2\n"
    "add a0, a0, t2\n"
    "add a1, a1, t2\n"

    // count decrement in its OWN EP so its writeback completes before the
    // branch reads t0 (avoids a sub->bnez RAW hazard inside one EP).
    "sub t0, t0, t1\n"
    "nop\n"
    "nop\n"

    // loop_end EP: the back-edge branch is the LAST instruction in the loop.
    // The previous structure packed `ret` into this same EP, so on a multi-strip
    // iteration the taken bnez still executed the trailing ret and ended the
    // task after one strip.  Keep bnez alone here; the ret lives in its own EP
    // below, reached only when the loop falls through (t0 == 0).
    "bnez t0, dwt_loop\n"
    "nop\n"
    "nop\n"

    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
