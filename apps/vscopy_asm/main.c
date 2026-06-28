// ============================================================================
// vscopy_asm — tightly-coupled (standard Ara) counterpart of vscopy_hdv.
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

#define TOTAL_ELEMENTS 1024

// 16-byte aligned HDV task entry used by the mock host/TB.
// Override with: make -C apps bin/vscopy_hdv HDV_TASK_ENTRY=0x80002000
#ifndef VSCOPY_HDV_TASK_ENTRY
#define VSCOPY_HDV_TASK_ENTRY 0x80001000UL
#endif

// Uniform AVL knob: build with `make bin/vscopy_asm asm_avl=<n>` to inject
// -DASM_AVL=<n>.  Defaults to TOTAL_ELEMENTS so a plain make is unchanged.
#ifndef ASM_AVL
#define ASM_AVL TOTAL_ELEMENTS
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// dst[i] = src[i]
void vscopy(int n, const float *src, float *dst);

int main() {
    HW_CNT_READY;
    #ifndef SPIKE
    perf_time();
    #endif
    vscopy(ASM_AVL, src1, src2);
    #ifndef SPIKE
    perf_time();
    #endif
    HW_CNT_NOT_READY;

    return 0;
}

__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void vscopy(int n, const float *src, float *dst) {
    // ABI on entry: a0 = n, a1 = src, a2 = dst.
    //
    // HDV packetisation (4 EPs per loop iteration):
    //   EP0 = vsetvli || vle(v0,src)              (sub tail-carries via cross=1)
    //   EP1 = sub || slli || add a1 || vse(dst)   (store snapshots current dst)
    //   EP2 = add a2                              (dst pointer bump)
    //   EP3 = bnez
    // On loop exit the fall-through ret terminates the HDV task.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vscopy_hdv_task_start:\n"

    "loop:\n"
    "vsetvli t0, a0, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "sub a0, a0, t0\n"

    // EP1: carried sub || slli || add a1 || vse.  vse reads the current dst base
    // a2; the increment of a2 is deferred to EP2, so the store sees the right
    // address.  slli writes the byte stride t1 that add a1 consumes in slot order.
    "slli t1, t0, 2\n"
    "add a1, a1, t1\n"
    "vse32.v v0, (a2)\n"

    "add a2, a2, t1\n"
    "bnez a0, loop\n"
    "ret\n"

    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
